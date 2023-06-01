import traceback
import re
from pathlib import Path

from dialop.envs import DialogueEnv, GameError
from dialop.games.optimization import OptimizationGame
from dialop.templates import OptimizationPromptTemplate

class OptimizationEnv(DialogueEnv):

    def __init__(self):
        self.players = ["player-1", "player-2"]
        instrs = (Path(__file__).parent / "data/optimization.txt").read_text()
        self.instructions = [instrs, instrs]

    def reset(self, game_state=None):
        if game_state is not None:
            self.game = OptimizationGame.create_from_game_state(game_state)
            self.game.action_log = game_state["action_log"]
        else:
            self.game = OptimizationGame({})
            self.game.reset()
        # Compute score range
        self.best_score = self.game.best_assignment_reward
        self.num_msgs = 0
        obss = self._init_from_action_log()
        return {**obss,
                "turn_player": self.players[self.game.turn_player],
                "done": False}

    def step(self, message):
        done = False
        reward = 0
        info = {"num_msgs": self.num_msgs}
        player = self.players[self.game.turn_player]
        try:
            m = self._parse_message(
                    message,
                    can_propose=True,
                    can_respond=True,
                    must_respond=(self.game.proposal is not None)
                    )
            type_ = m["mtype"]
            content = m["msg"]
            if type_ == "message":
                self.num_msgs += 1
                if player == "player-1":
                    obss = [message, f"\nPartner:{message}"]
                else:
                    obss = [f"\nPartner:{message}", message]
                self.game.message({
                        "data": content,
                        "from_player": self.game.turn_player,
                        "type": "utterance",
                })
            elif type_ == "propose":
                self.num_msgs += 1
                obss = self._propose(content)
            elif type_ == "accept" or type_ == "reject":
                self.num_msgs += 1
                done, game_infos = self._proposal_response(
                    type_ == "accept",
                    self.game.turn_player)
                info.update({
                    "score": self.game.proposal_reward,
                    "score_norm": self.game.proposal_reward / self.game.best_assignment_reward,
                })
                obss = ["", ""]
                obss[self.game.turn_player] = f" [{type_}]"
                obss[1 - self.game.turn_player] = f"\nPartner: [{type_}]"
            else:
                raise ValueError(f"Message type not found for: {message}.")
        except GameError as e:
            obss = ["", ""]
            obss[self.game.turn_player] = f"{message}\nError: {str(e)}"
        except Exception as e:
            print(f"!!! {traceback.format_exc()}")
            return {
                **{p: "error" for p in self.players},
                "done": False,
                "reward": 0,
                "turn_player": self.players[self.game.turn_player]
            }, True
        obss = {self.players[i]: obs for i, obs in enumerate(obss)}
        obss.update({
            "turn_player": self.players[self.game.turn_player],
            "done": done,
            "reward": reward,
            "info": info,
        })
        return obss, False

    def _propose(self, message):
        proposal = self._parse_proposal(message)
        self.game.propose(None, self.game.turn_player, proposal_ids=proposal)
        proposer = 1 - self.game.turn_player
        obss = ["", ""]
        obss[proposer] = message
        obss[self.game.turn_player] = (
            f"\nPartner: {message}"
            f"\nYou can output one of these choices: [accept] or [reject]")
        return obss

    def _init_from_action_log(self):
        obss = {}
        for i, player in enumerate(self.players):
            table = "\n".join([",".join(map(str, row)) for row in self.game.tables[i]])
            obss[player] = OptimizationPromptTemplate.render(
                table=table,
                messages=self.game.action_log,
                player_id=i,
                any=any,
            ).rstrip()
        return obss

    def _word_overlap_search(self, options, item):
        item_words = item.split(" ")
        scores = {}
        for option in options:
            scores[option] = 0
            option_words = option.split(" ")
            for word in option_words:
                if word in item_words:
                    scores[option] += 1
        return max(scores, key=scores.get)

    def _parse_proposal(self, message):
        pattern = r"\n|<br/>"
        proposal_lines = re.split(pattern, message)
        proposal_lines = [line.strip() for line in proposal_lines]
        proposal_lines = [line for line in proposal_lines if line]
        if proposal_lines[0] != "Proposal:" or len(proposal_lines) != self.game.num_rows + 1:
            raise GameError(
                f"Your proposal must start with 'Proposal:' and have {self.game.num_rows} lines, one for each slot."
            )
        proposal_lines = proposal_lines[1:]
        workers = self.game.WORKERS[:self.game.num_rows]
        tasks = self.game.TASKS[:self.game.num_cols]
        parsed_proposal = []
        parsed_proposal_indices = []
        for line in proposal_lines:
            line = line.split(":")
            if len(line) < 2:
                raise GameError(
                    "Each line of your proposal must be of the form "
                    "Paper: Reviewer"
                )
            task, worker = line[0].strip(), line[1].strip()
            task = self._word_overlap_search(tasks, task)
            worker = self._word_overlap_search(workers, worker)
            task_index = tasks.index(task)
            worker_index = workers.index(worker)
            # Don't allow duplicate tasks or workers:
            workers.pop(worker_index)
            tasks.pop(task_index)
            parsed_proposal.append((task, worker))
            parsed_proposal_indices.append((task_index, worker_index))
        return parsed_proposal_indices