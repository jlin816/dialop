import copy
import itertools
import random
import threading
import time
from datetime import datetime

from dialop.games.base_game import DialogueGame
from dialop.games.mediation_data import (Calendar, FlightSet, hr_delta,
                                        times_overlap, parse)


class MediationGame(DialogueGame):

    DEFAULT_CONFIG = {
        "num_players": 3, # including agent
        "num_flights": 30,
        "p_event": 0.35,
        "p_shared": 0.75,
        "take_turns": True,
    }

    def __init__(self, env_config):
        config = MediationGame.DEFAULT_CONFIG.copy()
        config.update(env_config)
        self.num_players = config["num_players"]
        self.num_flights = config["num_flights"]
        self.p_event = config["p_event"]
        # Create virtual rms with agent (id=self.num_players - 1) + each player
        self.virtual_rooms = [[i, self.num_players - 1] for i in
                              range(self.num_players - 1)]
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.disconnect = False

    @classmethod
    def create_from_game_state(cls, game_state):
        game = cls({})
        game.reset()
        game.action_log = game_state["action_log"]
        game.message_history = game_state["message_history"]
        game.arrival_time_pref = game_state["player_data"][0]["arrival_time_pref"]
        game.message_histories = game_state["message_histories"]
        for vroom in range(len(game.virtual_rooms)):
            turns = [a for a in game.action_log \
                           if a["vroom"] == vroom]
            if len(turns) > 0:
                last_player = turns[-1]["player"]
                other_idx = 1 - game.virtual_rooms[vroom].index(last_player)
                game.turn_players[vroom] = game.virtual_rooms[vroom][other_idx]
        game.player_data = game_state["player_data"]
        # Add flight ids to proposals
        for ac in game.action_log:
            if ac["type"] == "proposal":
                flight0 = game.player_data[0]["flights"].index(ac["proposals"][0]["proposal_data"])
                flight1 = game.player_data[1]["flights"].index(ac["proposals"][1]["proposal_data"])
                assert flight0 >= 0 and flight1 >= 0
                ac["proposals"][0]["flight_id"] = flight0
                ac["proposals"][1]["flight_id"] = flight1
        # Initialize proposal state
        for turn in game.action_log:
            if turn["type"] == "proposal":
                game.proposal = [ppl["proposal_data"] for ppl in turn["proposals"]]
                game.is_full_proposal = all(game.proposal)
        return game

    def reset(self):
        # NOTE: agent must be the last player
        self.action_log = []
        self.message_history = []
        self.arrival_time_pref = random.randint(1, 10)
        self.message_histories = [[] for i in range(self.num_players - 1)]
        self.accepts = [False] * len(self.virtual_rooms)
        # Global ids for the player taking the turn in each vroom
        self.turn_players = [i for i in range(self.num_players - 1)]
        self.scores = {}
        self.proposal = None

        player_data = []
        for _ in range(self.num_players - 1):
            cal = Calendar(self.p_event)
            flights = FlightSet("nyc", self.num_flights)
            # Remove flights that don't overlap with any events:
            flights.flights = [f for f in flights.flights if any(
                times_overlap((evt["start"], evt["end"]), (f["start"], f["end"])) for evt in cal.events
            )]
            price_pref = random.randint(1, 20)
            shared_calendar = copy.deepcopy(cal.events)
            shared_calendar = random.sample(shared_calendar, int(len(shared_calendar) * MediationGame.DEFAULT_CONFIG["p_shared"]))
            unshared_calendar = [evt for evt in cal.events if evt not in shared_calendar]

            player_data.append({
                "role": "human",
                "calendar": cal.events,
                "shared_calendar": shared_calendar,
                "unshared_calendar": unshared_calendar,
                "flights": flights.flights,
                "mean_price": flights.mean_price,
                "price_pref": price_pref,
                "arrival_time_pref": self.arrival_time_pref,
            })
        self.player_data = player_data
        data = player_data + [{
            "role": "agent",
            "player_data": [{
                "calendar": p["calendar"],
                "shared_calendar": p["shared_calendar"],
                "unshared_calendar": p["unshared_calendar"],
                "flights": p["flights"],
            } for p in player_data],
        }]
        return data

    def _take_turn(self, vroom):
        cur_player = self.virtual_rooms[vroom].index(self.turn_players[vroom])
        self.turn_players[vroom] = self.virtual_rooms[vroom][1 - cur_player]

    def message(self, message: str, vroom: int, metadata=None):
        metadata = metadata or {}
        self.message_history.append(message)
        self.message_histories[vroom].append({
            "player": self.turn_players[vroom],
            "message": message
        })
        self.action_log.append({
            **metadata,
            "type": "message",
            "message": message,
            "player": self.turn_players[vroom],
            "vroom": vroom,
            "time": time.time() - self.start_time
        })
        self._take_turn(vroom)

    def _calendar_cost(self, flight, cal):
        cost = 0
        conflicts = []
        for evt in cal:
            if times_overlap((evt["start"], evt["end"]),
                             (flight["start"], flight["end"])):
                cost -= evt["importance"]
                conflicts.append(evt)
        return int(cost), conflicts

    def _price_cost(self, flight, pd):
        reward = (flight["price"] - pd["mean_price"]) / pd["mean_price"]
        return int(-pd["price_pref"] * reward)

    def _arrival_timediff_cost(self, flights):
        cost = 0
        deltas = []
        for i in range(len(flights)):
            for j in range(i + 1, len(flights)):
                e1 = datetime.fromisoformat(flights[i]["end"])
                e2 = datetime.fromisoformat(flights[j]["end"])
                diff = e2 - e1 if e1 < e2 else e1 - e2
                # Deduct 1-10 for every 3 hours you're off
                delta = hr_delta(diff)
                cost -= self.arrival_time_pref * delta / 3
                deltas.append(delta)
        return int(cost), deltas

    def _score_proposal(self, proposal):
        """
        Args:
            proposal (List[Dict]): list of flight dicts, one for each player
        Returns:
            player_obss (List[Dict]): list of player observations with costs
            for the proposal
        """
        player_obss = []
        for i, pd in enumerate(self.player_data):
            calendar_cost, conflicts = self._calendar_cost(proposal[i], pd["calendar"])
            arrival_time_cost, deltas = self._arrival_timediff_cost(proposal)
            cost = {
                "calendar": calendar_cost,
                "price": self._price_cost(proposal[i], pd),
                "arrival_time": arrival_time_cost
            }
            cost["total"] = sum(cost.values())
            player_obss.append({"cost": cost, "conflicts": conflicts, "deltas": deltas})
        return player_obss

    def propose(self, proposal, from_player, metadata=None):
        metadata = metadata or {}
        self._reset_proposal_state()
        self.proposal = proposal
        # Empty slots are None
        self.is_full_proposal = all(proposal)
        for vroom_idx, vroom in enumerate(self.virtual_rooms):
            # Human is next in all rooms
            self.turn_players[vroom_idx] = vroom[0]
        player_obss = self._score_proposal(proposal)
        for i, player_psl in enumerate(self.proposal):
            player_obss[i]["proposal_data"] = player_psl
            player_obss[i]["proposal_readable"] = self.pp_flight(player_psl)
        self.action_log.append({
            **metadata,
            "type": "proposal",
            "proposals": player_obss,
            "vroom": None,
            "time": time.time() - self.start_time
        })
        return player_obss

    def _reset_proposal_state(self):
        self.proposal = None
        self.is_full_proposal = False
        # Note this step must be thread-safe since everyone is editing
        #  their individual self.accepts[i]
        with self.lock:
            for i in range(len(self.accepts)):
                self.accepts[i] = False
        print(self.accepts)
        if self.proposal is None:
            if self.accepts[0] or self.accepts[1]:
                import pdb; pdb.set_trace()

    def proposal_response(self, response, from_player, metadata=None):
        metadata = metadata or {}
        player_idx = from_player
        with self.lock:
            self.accepts[player_idx] = response["accept"]
        game_over = all(self.accepts)
        infos = [{}] * len(self.virtual_rooms)
        if game_over:
            if self.proposal is None:
                import pdb; pdb.set_trace()
            self.disconnect = False
            player_obss = self._score_proposal(self.proposal)
            reward = sum([obs["cost"]["total"] for obs in player_obss])
            infos = [{
                "reward": reward,
                "role": "agent" if i == self.num_players - 1 else "player",
                "player_reward": player_obss[i]["cost"]["total"] if i < len(player_obss) else 999,
            } for i in range(self.num_players)]
            self.scores = {
                "reward": reward,
                "player_rewards": [infos[i]["player_reward"] for i in range(self.num_players)]
            }
        # start from scratch, agent has to re-propose
        elif not response["accept"]:
            self._reset_proposal_state()
            reward = 0
            # self._take_turn(response["virtual_room_id"])
        self.action_log.append({
            **metadata,
            "type": "proposal_response",
            "response": response,
            "all_responses": copy.deepcopy(self.accepts),
            "game_over": game_over,
            "player": player_idx,
            "vroom": player_idx,
            "time": time.time() - self.start_time
        })
        return game_over, infos

    def _compute_all_solutions(self):
        combos = itertools.product(*[p["flights"] for p in self.player_data])
        scores = []
        for c in combos:
            obss = self._score_proposal(c)
            score = sum([obs["cost"]["total"] for obs in obss])
            scores.append(score)
        return scores

    def get_game_info(self):
        return {
            "player_data": self.player_data,
            "action_log": self.action_log,
            "disconnect": self.disconnect,
            "message_histories": self.message_histories,
            "message_history": self.message_history,
            "scores": self.scores
        }

    @staticmethod
    def pp_flight(flight):
        start = parse(flight["start"]).strftime("%-m/%-d% %-I:%M %p")
        end = parse(flight["end"]).strftime("%-I:%M %p")
        return f"{flight['carrier']} | {flight['price']} | {start} - {end}"

    @staticmethod
    def pp_event(event, show_importance):
        start = parse(event["start"]).strftime("%-m/%-d% %-I:%M %p")
        end = parse(event["end"]).strftime("%-I:%M %p")
        if show_importance:
            string = f"({event['importance']}) | {start} - {end}"
        else:
            string = f"{start} - {end}"
        string = string.replace(":00", "")
        return string