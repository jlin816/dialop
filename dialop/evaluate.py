from copy import deepcopy
import json
import os
import pathlib
import time
from typing import Optional, Literal
from itertools import cycle

from openai.error import APIConnectionError, RateLimitError
import numpy as np
import tyro
from ruamel.yaml import YAML
from rich import print
from rich.console import Console
console = Console()

from envs import (
    ItineraryEnv,
    MatchingEnv,
    MediationEnv,
    WordLimit,
    ForceProposal,
    AsymmetricForceProposal
)
from players import (
    LLMPlayer,
    HumanPlayer,
    DryRunPlayer,
    OutOfContextError
)
from utils import Logger, retry, count_words

FPATH = pathlib.Path(os.path.dirname(os.path.realpath(__file__)))
RESDIR = pathlib.Path("/Users/user/coop/collaborative-dialogue/results/")
#RESDIR = pathlib.Path("/Users/user/Projects/collaborative-dialogue/results/")
DATADIR = pathlib.Path("/Users/user/coop-dialog-data/data/")

GAME_CLSS = {
    "matching": MatchingEnv,
    "itinerary": ItineraryEnv,
    "mediation": MediationEnv,
}

class ResampleError(Exception):
    pass

def selfplay(
    game_cls,
    games,
    samples_per_game,
    resume,
    end
):
    for game_idx, game in enumerate(games[resume:end]):
#        data = game["games"][0]
        original_log = game["action_log"]
        data = deepcopy(game)
        # Clear action log so env doesn't initialize with a message history
        data["action_log"] = []
        if game_cls == MatchingEnv:
            score = data["proposal_reward"]
            score_norm = data["result"]["norm"]
        else:
#            score = data["action_log"][-3]["scores"]["total"]
            score = data["result"]["score"]
            score_norm  = data["result"]["norm"]
        metadata = {
            "hh_turns": len(original_log),
            "hh_words": count_words(original_log),
            "hh_score": score,
            "hh_score_norm": score_norm,
        }
        for sidx in range(samples_per_game):
            name = f"{game_idx + resume}_{sidx}"
            yield data, name, metadata

def prompted_selfplay(
    game_cls,
    games,
    samples_per_game,
    resume,
    end,
):
    for game_idx, game in enumerate(games[resume:end]):
        if game_cls == MatchingEnv:
            data = deepcopy(game)
            original_log = game["action_log"]
        elif game_cls == ItineraryEnv:
            data = deepcopy(game)
            original_log = game["action_log"]
        elif game_cls == MediationEnv:
            data = deepcopy(game)
            original_log = game["action_log"]

        if game_cls == ItineraryEnv:
            try:
                score = data["action_log"][-3]["scores"]["total"]
            except:
                for turn in range(0, len(data["action_log"])):
                    if data["action_log"][turn]["type"] == "proposal":
                        score = data["action_log"][turn]["scores"]["total"]
        elif game_cls == MatchingEnv:
            score = data["proposal_reward"]
        elif game_cls == MediationEnv:
            score = data["result"]["score"]

        total_word_count = count_words(original_log)
        prefix_word_counts = []
        for turn in range(0, len(data["action_log"])):
            num_words = count_words(original_log[:turn])
            prefix_word_counts.append(num_words)
        # Get turns closest to 25%, 50%, 75% of the way through the game:
        turn_idxs = []
        # for pct in [0.25, 0.5, 0.75]:
        for pct in [0.5, 0.75]:
            turn_idxs.append(
                np.argmin(np.abs(np.array(prefix_word_counts) - pct * total_word_count))
            )
        # Get index of final proposal:
        proposal_idx = None
        for turn in range(0, len(data["action_log"])):
            if data["action_log"][turn]["type"] == "proposal":
                proposal_idx = turn
        if proposal_idx is None:
            raise ValueError("Game doesn't include a proposal")
        turn_idxs.append(proposal_idx)

        # import pdb; pdb.set_trace()
        # for turn in range(0, len(data["action_log"])):
        names = ["50", "75", "end"]
        # for turn in range(2, len(data["action_log"]) // 2):
        #     end = 2 * (turn + 1)
        for name, end in zip(names, turn_idxs):
            # if end >= len(game["games"][0]["action_log"]): continue
            data["action_log"] = original_log[:end]
            metadata = {
                "initialized_turns": len(data["action_log"]),
                "initialized_words": count_words(data["action_log"]),
                "hh_turns": len(original_log),
                "hh_words": count_words(original_log),
                "hh_score": score,
                "hh_score_norm": data["result"]["norm"],
            }
            for sidx in range(samples_per_game):
                name = f"{game_idx + resume}_start{len(data['action_log'])}_{name}_{sidx}"
                yield data, name, metadata

@retry(allowed_exceptions=[OutOfContextError, RateLimitError, ResampleError])
def run(
    game_cls,
    data,
    metadata,
    player_ctor,
    env_ctor,
    logfile,
    use_word_limit=False,
    max_length=3
):
    # Create players.
    players = player_ctor()
    # Create env.
    env = env_ctor()
    # TODO: make api the same
    if use_word_limit:
        obss = env.reset(word_limit=metadata["hh_words"],
                         game_state=data)
    else:
        obss = env.reset(game_state=data)

    # Log initial info.
    log = Logger(logfile)
    for pname, player in players.items():
        log.write(
            f"{pname} params",
            json.dumps(getattr(player, 'model_kwargs', {}), indent=2))
        log.write(f"{pname} prompt", player.prompt)
    if game_cls == ItineraryEnv:
        if env.query_executor == "gpt3":
            log.write(f"Query Executor Prompt", env.search.prompt)
        else:
            log.write("Using deterministic query executor.")

    # Env loop.
    t = 0
    player_cycle = cycle(players.keys())
    if game_cls == MediationEnv:
        while not obss["done"] and t < max_length:
            console.rule("environment obs")
            console.print(obss)
            [player.observe(obss[pname]) for pname, player in players.items()]
            for pname in players:
                log.log(key=pname, value=obss[pname], title=f"obs t={t}")

            # Cycle through players, letting them speak if it's their turn
            next_player = next(player_cycle)
            while next_player not in obss["turn_players"]:
                next_player = next(player_cycle)
            resample = True
            resample_cnt = 0
            while resample and resample_cnt < 3:
                if resample_cnt >= 1:
                    console.print("INVALID: resampling...", style="bold red")
                stepped = False
                while not stepped:
                    try:
                        resp = players[next_player].respond()
                        stepped = True
                    except RateLimitError:
                        print("Rate limited. Sleeping...")
                        time.sleep(30)
                log.log(
                    key=next_player,
                    value=resp,
                    title=f"generate t={t} try={resample_cnt}"
                )
                stepped = False
                while not stepped:
                    try:
                        obss, resample = env.step(resp, next_player)
                        stepped = True
                    except RateLimitError:
                        print("Rate limited during environment step. Sleeping...")
                        time.sleep(30)
                resample_cnt += 1
            t += 1
    else:
        while not obss["done"] and t < max_length:
            console.rule("environment obs")
            console.print(obss)
            [player.observe(obss[pname]) for pname, player in players.items()]
            for pname in players:
                log.log(key=pname, value=obss[pname], title=f"obs t={t}")
            resample = True
            resample_cnt = 0
            while resample and resample_cnt < 3:
                if resample_cnt >= 1:
                    console.print("INVALID: resampling...", style="bold red")
                stepped = False
                while not stepped:
                    try:
                        resp = players[obss["turn_player"]].respond()
                        stepped = True
                    except RateLimitError:
                        print("Rate limited. Sleeping...")
                        time.sleep(30)
                log.log(
                    key=obss["turn_player"],
                    value=resp,
                    title=f"generate t={t} try={resample_cnt}"
                )
                stepped = False
                while not stepped:
                    try:
                        obss, resample = env.step(resp)
                        stepped = True
                    except RateLimitError:
                        print("Rate limited on step. Sleeping...")
                        time.sleep(30)
                resample_cnt += 1
            t += 1

    if resample_cnt >= 3:
        print("Resampled too many times.")
        raise ResampleError()

    log.flush()
    for pname, player in players.items():
        log.flush_key(pname, title=f"{pname} Log")
        log.write(f"Final {pname} Prompt", player.prompt)
    result = {**obss, **metadata, "t": t,
              "num_turns": len(env.game.action_log),
              "num_words": count_words(env.game.action_log)}
    log.write("Result", json.dumps(result))
    log.flush()
    log.close()


def main(
    exp_name: str,
    game: Literal["matching", "itinerary", "mediation"],
    mode: Literal["selfplay", "prompted_sp"],
    resume: Optional[int]=0,
    end: Optional[int]=1000,
    samples_per_game: Optional[int]=1,
    temperature: Optional[float]=0.1,
    dry_run: Optional[bool]=True,
    use_word_limit: Optional[bool]=False,
):

    game_cls = GAME_CLSS[game]
    EXP_DIR = RESDIR / game
    if game_cls == MatchingEnv:
        DATA_PATH = DATADIR / "reviewer.jsonl.post"
    elif game_cls == ItineraryEnv:
        DATA_PATH = DATADIR / "itinerary.jsonl.post"
    elif game_cls == MediationEnv:
        DATA_PATH = DATADIR / "mediation.jsonl.post"

    os.makedirs(EXP_DIR / exp_name, exist_ok=True)
    with open(DATA_PATH) as f:
        games = []
        for line in f:
            games.append(json.loads(line))

    # Create generator for eval mode.
    if mode == "selfplay":
        gen = selfplay(game_cls, games, samples_per_game, resume, end)
    elif mode == "prompted_sp":
        gen = prompted_selfplay(game_cls, games, samples_per_game, resume, end)
    else:
        raise NotImplementedError()

    def create_players():
        print("Initializing players...")
        # Create prompts.
        if game_cls == MatchingEnv:
            with open(FPATH / "prompts" / "matching_prompt.txt") as f:
                matching_prompt = f.read()
        elif game_cls == ItineraryEnv:
            # if use_word_limit:
            #     with open(FPATH / "prompts" / "itinerary_agent_timed.txt") as f:
            #         agent_prompt = f.read()
            #     with open(FPATH / "prompts" / "itinerary_user_timed.txt") as f:
            #         user_prompt = f.read()
            # else:
            with open(FPATH / "prompts" / "itinerary_agent.txt") as f:
                agent_prompt = f.read()
            with open(FPATH / "prompts" / "itinerary_user.txt") as f:
                user_prompt = f.read()
        elif game_cls == MediationEnv:
            with open(FPATH / "prompts" / "mediation_agent.txt") as f:
                agent_prompt = f.read()
            with open(FPATH / "prompts" / "mediation_user0.txt") as f:
                user0_prompt = f.read()
            with open(FPATH / "prompts" / "mediation_user1.txt") as f:
                user1_prompt = f.read()

        if game_cls == MatchingEnv:
            p1, p2 = "player-1", "player-2"
            p1_prompt, p2_prompt = matching_prompt, matching_prompt
            optional1 = p1_prompt[
                p1_prompt.index("EXAMPLE 1"):]
            optional1 = optional1[:optional1.index("EXAMPLE 2")]
            optional2 = p2_prompt[
                p2_prompt.index("EXAMPLE 2"):]
            optional2 = optional2[:optional2.index("EXAMPLE 2")]
        elif game_cls == ItineraryEnv:
            p1, p2 = "agent", "user"
            p1_prompt, p2_prompt = agent_prompt, user_prompt
            optional1, optional2 = None, None
        elif game_cls == MediationEnv:
            p1, p2, p3 = "user0", "user1", "agent"
            optional = agent_prompt[agent_prompt.index("User 0 Information"):]
            optional = optional[:optional.index("\n\n") + 2]

        if dry_run:
            assert game_cls != MediationEnv
            players = {p1: DryRunPlayer(p1_prompt, p1, console),
                       p2:  DryRunPlayer(p2_prompt, p2, console)}
        elif game_cls == MediationEnv:
            players = {p1: LLMPlayer(user0_prompt, p1, console,
                                     model_kwargs={"temperature": temperature}),
                       p2:  LLMPlayer(user1_prompt, p2, console,
                                      model_kwargs={"temperature": temperature}),
                       p3:  LLMPlayer(agent_prompt, p3, console,
                                      prefix="\nYou to",
                                      optional=optional,
                                      model_kwargs={"temperature": temperature})}
        else:
            players = {p1: LLMPlayer(p1_prompt, p1, console,
                                     optional=optional1,
                                     model_kwargs={"temperature": temperature}),
                       p2:  LLMPlayer(p2_prompt, p2, console,
                                      optional=optional2,
                                      model_kwargs={"temperature": temperature})}
        return players

    def create_env():
        print("Initializing envs...")
        if game_cls == MatchingEnv:
            env = MatchingEnv()
            if use_word_limit:
                env = ForceProposal(env, ["player-1", "player-2"])
        elif game_cls == ItineraryEnv:
            env = ItineraryEnv(query_executor="gpt3")
            if use_word_limit:
                env = AsymmetricForceProposal(env, ["agent"])
        elif game_cls == MediationEnv:
            env = MediationEnv()
            if use_word_limit:
                env = AsymmetricForceProposal(env, ["agent"])
        return env

    if dry_run:
        max_length = 15
    elif game_cls == MediationEnv:
        max_length = 45
    else:
        max_length = 30

    # Evaluate.
    times = []
    for i, (data, fname, metadata) in enumerate(gen):
        if (EXP_DIR / exp_name / f"{fname}.out").exists():
            continue
        if not dry_run and i % 20 == 1:
            print(f"Sleeping... {np.mean(times):.1f}")
            time.sleep(30)
            pass
        print(fname)

        start = time.time()
        run(
            game_cls,
            data,
            metadata,
            create_players,
            create_env,
            EXP_DIR / exp_name /f"{fname}.out",
            use_word_limit=use_word_limit,
            max_length=max_length,
        )
        elapsed = (time.time() - start) / 60
        times.append(elapsed)
        print(f" == Finished {i} {elapsed:.1f} == ")

    exit()

    #with open("query_executor_prompt.txt", "w") as f:
    #    f.write(env.search.prompt)
    #test_queries = [
    #    "Search(fields=[name], text_query='not touristy', filters=[category == restaurant]"
    #]
    #env.search(test_queries[0])

    # Try scoring a proposal
    #proposal = "[The Dive, Saul's, NULL]"
    #proposal_info = env._propose(proposal)
    #print(proposal_info)


if __name__ == "__main__":
    tyro.cli(main)
