from __future__ import annotations
import itertools
import os
import random
import json
import time
from collections import defaultdict
from flask import current_app, has_request_context
import numpy as np
from ruamel.yaml import YAML
yaml = YAML(typ='safe')

from dialop.games.base_game import DialogueGame
from dialop.games.planning_data import (
    Event, PREF_NAME_TO_CLS, ALL_PREFS, ALL_CONSTRAINTS, DistancePreference,
)

## Game logic

class PlanningGame(DialogueGame):

    DEFAULT_CONFIG = {
        "num_events": -1,
        "num_slots": 3,
        "num_prefs": 10,
    }

    def __init__(self, env_config):
        config = PlanningGame.DEFAULT_CONFIG.copy()
        config.update(env_config)
        self._load_data()
        self.num_events = config["num_events"] if config["num_events"] > 0 \
            else len(self.game_data["all_events"])
        self.num_slots = config["num_slots"]
        self.num_prefs = config["num_prefs"]
        assert len(self.all_events) >= self.num_events
        assert self.num_events > self.num_slots
        self.disconnect = True

    @classmethod
    def create_from_game_state(cls, game_state):
        """Creates a game from an offline game state.
        Only instantiates the state needed to score proposals (events,
        features, and preferences).
        Note game.events is kept as a list of dicts, instead of Event objects.
        """
        game = cls({})
        game.reset()
        game.action_log = game_state["action_log"]
        game.events = game_state["events"]
        for e in game.events:
            e["type"] = "event"
        game.prefs = []
        for pref in game_state["preferences"]:
            if len(pref) != 4:
                import pdb; pdb.set_trace()
            desc, wt, cls, cls_args = pref
            game.prefs.append(PREF_NAME_TO_CLS[cls](**cls_args))
        if len(game.action_log) > 0:
            last_player = game.action_log[-1]["player"]
            game.turn_player = 1 - last_player
        game.message_history = [m["message"] for m in game.action_log \
                                if m["type"] == "message"]
        # Set state if there's a proposal on the table
        for turn in game.action_log:
            if turn["type"] == "proposal":
                proposal = turn["proposal"]
                game.proposal = proposal
                game.proposal_readable = str(proposal)
                game.is_full_proposal = all(proposal)
        game.best_sampled_score = None # only needed for human UI
        return game

    def _load_data(self):
        # Check whether we're running locally or in a flask server
        if has_request_context():
            dataf = os.path.join(current_app.static_folder, "travel_data.yaml")
            locf = os.path.join(current_app.static_folder, "locations.geojson")
        else:
            dirname = os.path.dirname(__file__)
            dataf = f"{dirname}/data/planning.yaml"
            locf = f"{dirname}/data/locations.geojson"
        self.game_data = yaml.load(open(dataf, "r"))
        locs = [x["geometry"]["coordinates"] for x in \
                json.load(open(locf, "r"))["features"]]
        random.shuffle(locs)
        all_events = self.game_data["all_events"]
        self.features = self.game_data["features"]
        self.all_types = self.game_data["all_types"]
        self.feats_by_type = {typ: [] for typ in self.all_types}
        for feat, info in self.features.items():
            typs = info["event_types"] if "event_types" in info else self.all_types
            for t in typs:
                self.feats_by_type[t].append({"name": feat, "info": info})
        self.all_events = [
            Event(id_=i,
                  name=e["name"],
                  etype=e["type"],
                  loc=locs[i],
                  est_price=random.choice(range(*self.all_types[e["type"]]["price_range"], 10))
            ) for i, e in enumerate(all_events)]

    def _randomize_event_features(self, event: Event):
        feats = random.sample(self.feats_by_type[event.etype], k=5)
        evt_feats = {}
        for feat in feats:
            if feat["info"]["type"] == "bool":
                evt_feats[feat["name"]] = random.choice([True, False])
            elif feat["info"]["type"] == "categorical":
                evt_feats[feat["name"]] = random.choice(feat["info"]["values"])
            else:
                raise NotImplementedError
        event.features = evt_feats
        return event

    def _compute_all_solutions(self, sample=False):
        """Brute force compute scores for all proposals."""
        if isinstance(self.events[0], Event):
            convert = lambda e: e.__dict__
        else:
            convert = lambda e: e
        if sample:
            solns = [[convert(e) for e in random.sample(self.events, k=3)] \
                     for _ in range(100)]
        else:
            solns = [[convert(e) for e in proposal] for proposal in \
                     itertools.permutations(self.events, r=3)]
        scores = []
        for soln in solns:
            soln = [
                soln[0],
                {"type": "travel", "data": str(self._dist(soln[0]["loc"],
                                                          soln[1]["loc"]))},
                soln[1],
                {"type": "travel", "data": str(self._dist(soln[1]["loc"],
                                                          soln[2]["loc"]))},
                soln[2]
            ]
            sc, _, _ = self._score_proposal(soln)
            scores.append(round(sum(sc)))
        return scores

    def _dist(self, loc1, loc2):
        dist = np.linalg.norm(np.array(loc1) - np.array(loc2))
        dist *= 69
        dist = round(dist * 10) / 10
        return dist

    def reset(self):
        self.action_log = []
        self.start_time = time.time()
        # Generate event set
        events = random.sample(self.all_events, self.num_events)
        self.events = [self._randomize_event_features(e) for e in events]
        # Generate preferences by type
        all_prefs = []
        for p in ALL_PREFS:
            all_prefs += p.generate(self.game_data)
        random.shuffle(all_prefs)
        self.prefs = all_prefs[:self.num_prefs] + \
            DistancePreference.generate(self.game_data)
        self.message_history = []
        self.turn_player = 0
        self.proposal = None
        self.best_sampled_score = max(self._compute_all_solutions(sample=True))

        obs_h = {
            "role": "human",
            "num_slots": self.num_slots,
            "preferences": [p.readable for p in self.prefs],
            "best_random_score": self.best_sampled_score,
        }
        obs_c = {
            "role": "agent",
            "num_slots": self.num_slots,
            "events": [e.__dict__ for e in self.events],
        }
        return obs_h, obs_c

    def message(self, message, metadata=None):
        metadata = metadata or {}
        self.message_history.append(message)
        self.action_log.append({
            **metadata,
            "type": "message",
            "message": message,
            "player": self.turn_player,
            "time": time.time() - self.start_time
        })
        self._take_turn()

    def propose(self, proposal, from_player, metadata=None):
        metadata = metadata or {}
        self.proposal = proposal
        self.proposal_readable = str(proposal)
        # Empty slots are None
        self.is_full_proposal = all(proposal)
        # self._take_turn()
        scores, scores_by_event, itinerary_scores = self._score_proposal(proposal)
        total_score = round(sum(scores))
        price = sum([e["est_price"] for e in proposal if e is not None and "est_price" in e])
        self.action_log.append({
            **metadata,
            "type": "proposal",
            "proposal": proposal,
            "scores": {
                "total": total_score,
                "scores_by_event": scores_by_event,
                "itinerary_scores": itinerary_scores,
                "scores": scores
            },
            "player": from_player,
            "time": time.time() - self.start_time
        })
        return {"proposal_data": proposal,
                "total_score": total_score,
                "evt_scores": scores_by_event,
                "itinerary_scores": itinerary_scores,
                "price": price,
                "is_full_proposal": self.is_full_proposal}

    def _score_proposal(self, proposal):
        """Scores a proposal of E events according to N preferences.

        Returns:
            scores (List[int] of length N):
                scores according to each preference
            scores_by_event (List[int] of length E):
                per-event scores, summed over preferences that apply to individual events
            itinerary_scores (List[Dict] of length <=N):
                full itinerary scores and descriptions, for preferences that apply to full
                itineraries
        """
        scores, scores_by_event = list(zip(*[p.score(proposal) for p in self.prefs]))
        # Get the preferences specifically over full itineraries
        itinerary_scores = [{"desc": p.readable, "score": sc} for sc, per_evt_sc, p in \
                            zip(scores, scores_by_event, self.prefs) \
                            if per_evt_sc is None]
        # Sum over all preferences to get total scores by event
        scores_by_event = np.array([s for s in scores_by_event if s is not None]).sum(axis=0)
        scores_by_event = scores_by_event.tolist()
        return scores, scores_by_event, itinerary_scores

    def proposal_response(self, response, from_player, metadata=None):
        metadata = metadata or {}
        if response["accept"]:
            game_over = self.is_full_proposal
            if game_over:
                self.disconnect = False
            scores, _, _ = self._score_proposal(self.proposal)
            reward = sum(scores)
        else:
            game_over = False
            self.proposal = None
            self.is_full_proposal = False
            reward = 0
        self.action_log.append({
            **metadata,
            "type": "proposal_response",
            "response": response,
            "player": from_player,
            "time": time.time() - self.start_time
        })
        infos = [{
            "reward": reward,
            "best_random_score": self.best_sampled_score,
        } for i in range(2)]
        return game_over, infos

    def get_game_info(self):
        return {
            "events": [e.__dict__ for e in self.events],
            "features": self.features,
            "preferences": [(p.readable, p.weight, type(p).__name__, p.__dict__) for p in self.prefs],
            "action_log": self.action_log,
            "disconnect": self.disconnect
        }
