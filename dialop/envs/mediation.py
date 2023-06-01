import re
import traceback
from pathlib import Path
from typing import Dict

from dialop.envs import DialogueEnv, GameError
from dialop.games import MediationGame
from dialop.templates import (MediationAgentPromptTemplate,
                              MediationProposalTemplate,
                              MediationUserPromptTemplate)

pp_flight = MediationGame.pp_flight
pp_event = MediationGame.pp_event

class MediationEnv(DialogueEnv):

    def __init__(self):
        self.players = ['user0', 'user1', 'agent']
        datapath = Path(__file__).parent / "data"
        self.instructions = [
            (datapath / "mediation_user.txt").read_text(),
            (datapath / "mediation_user.txt").read_text(),
            (datapath / "mediation_agent.txt").read_text()
            ]

    def reset(self, game_state=None):
        if game_state is not None:
            self.game = MediationGame.create_from_game_state(game_state)
        else:
            self.game = MediationGame({})
            self.game.reset()
        all_scores = self.game._compute_all_solutions()
        self.best_score = max(all_scores)
        self.worst_score = min(all_scores)
        self.num_msgs = 0
        obss = self._init_from_action_log()
        return {**obss,
                "turn_players": [self.players[p] for p in self.game.turn_players],
                "done": False}

    def step(self, message, player):
        done = False
        reward = 0
        info = {"num_msgs": self.num_msgs}
        try:
            m = self._parse_message(
                message,
                can_propose=(player == "agent"),
                can_respond=(player != "agent"),
                must_respond=(player != "agent" and self.game.proposal is not None),
                has_recipient=(player == "agent"))
            type_ = m["mtype"]
            content = m["msg"]
            vroom = m["vroom"] if player == "agent" else \
                self.players.index(player)
            if vroom != "all":
                vroom = int(vroom)
                if self.players[self.game.turn_players[vroom]] != player:
                    raise GameError("It is not your turn there. Try talking to "
                                    "the other user.")
            if type_ == "message":
                self.num_msgs += 1
                obss = ["", "", ""]
                if player == "agent":
                    obss[vroom] = f"\nAgent: [message] {content}"
                    obss[2] = f" {vroom}: [message] {content}"
                else:
                    obss[vroom] = message
                    obss[2] = f"\nUser {vroom}: {message}"
                self.game.message({
                        "data": content,
                        "from_player": self.game.turn_players[vroom],
                        "type": "utterance",
                        "virtual_room_id": vroom,
                }, vroom)
            elif type_ == "propose":
                if player != "agent":
                    raise GameError("Only the agent can make proposals.")
                self.num_msgs += 1
                obss = self._propose(content)
            elif type_ == "accept" or type_ == "reject":
                if player == "agent":
                    raise GameError("Only users can accept or reject.")
                self.num_msgs += 1
                done, infos = self._proposal_response(
                    type_ == "accept",
                    vroom)
                reward = infos[0].get("reward", 0)
                if done:
                    info.update({
                        "best_score": self.best_score,
                        "worst_score": self.worst_score,
                        "reward_normalized": ((reward - self.worst_score) /
                            (self.best_score - self.worst_score))
                    })
                obss = ["", "", ""]
                obss[vroom] = message
                obss[2] = f"\nUser {vroom}: {message}"
            else:
                raise ValueError(f"Message type not found for: {message}.")
        except GameError as e:
            obss = {p: "" for p in self.players}
            obss[player] = f"{message}\nError: {str(e)}"
            return {
                **obss,
                "done": False,
                "reward": 0,
                "turn_players": [self.players[p] for p in self.game.turn_players]
            }, False
        except Exception as e:
            print(f"!!! {traceback.format_exc()}")
            return {
                **{p: "error" for p in self.players},
                "done": False,
                "reward": 0,
                "turn_players": [self.players[p] for p in self.game.turn_players]
            }, True
        obss = {self.players[i]: obs for i, obs in enumerate(obss)}
        if type_ == "propose":
            obss["user0"] += "\nYou:"
            obss["user1"] += "\nYou:"
        else:
            next_player = self.players[self.game.turn_players[vroom]]
#            obss[next_player] += "\nYou to" if next_player == "agent" else "\nYou:"
        obss.update({
            "turn_players": [self.players[p] for p in self.game.turn_players],
            "done": done,
            "reward": reward,
            "info": info
        })
        return obss, False

    def _propose(self, message):
        # Parse proposal from the message
        # r"(?P<carrier>\w+) | \$(?P<price>[0-9]+) | [(?P<start>.*?)] - [(?P<end>.*?)]$",
        proposal = []
        m = re.match(
            r"user 0: id (?P<flight0>\d+), user 1: id (?P<flight1>\d+)$",
            message.strip()
        )
        if m is None:
            raise GameError(
                f"Proposal must be formatted like 'user 0: "
                "id <flight number>, user 1: id <flight number>'.")
        try:
            proposal = [
                self.game.player_data[0]["flights"][int(m["flight0"])],
                self.game.player_data[1]["flights"][int(m["flight1"])],
            ]
        except IndexError:
            raise GameError(
                f"Flight id for user 0 must be in [0, "
                f"{len(self.game.player_data[0]['flights'])-1}] and for user 1 "
                f" must be in [0, {len(self.game.player_data[1]['flights'])-1}]"
            )
        # Send to game, get scores
        proposal_infos = self.game.propose(proposal,
                                           self.players.index("agent"))
        obss = [self._format_proposal(info, i) for i, info in
                enumerate(proposal_infos)]
        obss[0] = f"Agent: [propose] {obss[0]}"
        obss[1] = f"Agent: [propose] {obss[1]}"
        obs_agent = (
            f" all: [propose] {message}"
            f"\nFlight for user 0: {pp_flight(proposal[0])}"
            f"\nFlight for user 1: {pp_flight(proposal[1])}"
        )
        obss.append(obs_agent)
        return obss

    def _init_from_action_log(self):
        # Make prompt for users
        obss = {}
        for pid in [0, 1]:
            msgs = [m for m in self.game.action_log if m["vroom"] == pid]
            data = self.game.player_data[pid]
            obss[self.players[pid]] = MediationUserPromptTemplate.render(
                player_id=pid,
                flights=data["flights"],
                unshared_calendar=data["unshared_calendar"],
                shared_calendar=data["shared_calendar"],
                messages=self.game.action_log,
                pp_flight=pp_flight,
                pp_event=pp_event,
                format_proposal=self._format_proposal,
            ).rstrip()
        obss["agent"] = MediationAgentPromptTemplate.render(
            player_data=self.game.player_data,
            messages=self.game.action_log,
            pp_flight=pp_flight,
            pp_event=pp_event,
        ).rstrip()
        return obss

    def _format_proposal(self, proposal: Dict, for_player: int):
        flight = None
        for i, f in enumerate(self.game.player_data[for_player]["flights"]):
            if f == proposal["proposal_data"]:
                flight = f
                break
        if not f:
            raise ValueError("Flight not found in flight set.")

        return MediationProposalTemplate.render(
            flight_id=i,
            flight=flight,
            proposal=proposal,
            pp_flight=pp_flight,
            pp_event=pp_event,
        )
