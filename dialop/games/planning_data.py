from abc import ABC, abstractmethod
from dataclasses import dataclass
import random
from typing import List, Optional, Tuple, Dict

import numpy as np

MAX_PREF_WEIGHT = 10
def random_pref():
    return random.randint(-MAX_PREF_WEIGHT, MAX_PREF_WEIGHT)
def random_pref_pos():
    return random.randint(1, MAX_PREF_WEIGHT)
def rand_size(lst):
    return random.choice(range(len(lst)))

@dataclass
class Event:
    id_: int
    name: str
    etype: str
    loc: Tuple[float, float]
    est_price: float
    features: Optional[dict] = None
    type: str = "event"

class SimpleRepr(object):
    """A mixin implementing a simple __repr__."""
    def __repr__(self):
        return "<{cls_name} {attrs}>".format(
            cls_name=self.__class__.__name__,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items()),
            )

class Constraint(ABC, SimpleRepr):
    @classmethod
    @abstractmethod
    def generate(cls, event_set: List[Event], features: List[Dict]) -> "Constraint":
        """Generate a randomized instance of this constraint from a set of events."""
        pass

    @abstractmethod
    def is_satisfied(self, itinerary: List[Optional[Dict]]) -> bool:
        """Return True if the itinerary satisfies this constraint."""
        pass


class Preference(ABC, SimpleRepr):
    @classmethod
    @abstractmethod
    def generate(cls, game_data: Dict) -> List["Preference"]:
        pass

    @abstractmethod
    def score(
        self,
        itinerary: List[Optional[Dict]],
    ) -> Tuple[float, Optional[List[float]]]:
        """Score the itinerary according to this preference.
        Returns the total score of the itinerary and additionally per-event
        scores, if applicable (None if this is a trajectory-level preference).
        """
        pass


## Custom constraints and preferences

class WantToGo(Preference):
    """Preference to go to a specific event or set of events."""
    def __init__(self, event_set, weight, penalize, readable):
        assert weight >= 0, "WantToGo weight has to be positive."
        self.event_set = event_set
        self.weight = weight
        self.penalize = penalize
        self.readable = readable

    @classmethod
    def generate(cls, game_data):
        # Pick a single event
        if np.random.random() < .25:
            event_set = [random.choice(game_data["all_events"])["name"]]
        # or a subset of events of the same type
        else:
            etype = random.choice(list(game_data["all_types"].keys()))
            evts = [e["name"] for e in game_data["all_events"] if e["type"] == etype]
            event_set = random.sample(
                evts,
                k=random.choice(range(1, min(3, len(evts))))
            )
        penalize = random.choice([True, False])
        if len(event_set) == 1:
            desc = f"definitely want to go to {event_set[0]}" if penalize else \
                f"heard good things about {event_set[0]}"
        else:
            desc = f"definitely want to check out Dan's recommendations: {', '.join(event_set)}" \
                if penalize else f"heard these {etype}s were good: {', '.join(event_set)}"
        return [cls(event_set, random_pref_pos(), penalize, desc)]

    def score(self, itinerary):
        for evt in itinerary:
            if evt is not None and evt["type"] == "event" and \
                    evt["name"] in self.event_set:
                return self.weight, None
        return -self.weight if self.penalize else 0, None

class AtLeastOneEventType(Preference):
    """Go to at least one {restaurant, shopping mall, etc.}."""
    def __init__(self, etype, weight, penalize, readable):
        assert weight > 0
        self.etype = etype
        self.weight = weight
        self.penalize = penalize
        self.readable = readable

    @classmethod
    def generate(cls, game_data):
        etype = random.choice(list(game_data["all_types"].keys()))
        desc = f"go to at least one {etype}"
        penalize = random.choice([True, False])
        return [cls(etype, random_pref_pos(), penalize, desc)]

    def score(self, itinerary):
        for evt in itinerary:
            if evt is None or evt["type"] != "event":
                continue
            if evt["etype"] == self.etype:
                return self.weight, None
        return -self.weight if self.penalize else 0, None

class MaxN(Constraint):
    """Max N events of a certain type."""
    def __init__(self, etype, n):
        self.etype = etype
        self.n = n
        self.readable = self._generate_readable()

    def _generate_readable(self):
        return f"Max {self.n} {self.etype}s"

    @classmethod
    def generate(cls, event_set, features):
        all_typs = list(set([e.etype for e in event_set]))
        etype = random.choice(all_typs)
        n = random.choice(range(1,4))
        return cls(etype, n)

    def is_satisfied(self, itinerary):
        num_of_type = len([e for e in itinerary if e and \
                           e["type"] == "event" and \
                           e["etype"] == self.etype])
        return num_of_type <= self.n

    @property
    def description(self):
        return f"Don't want to go to more than {self.n} {self.etype}s"

## GENERAL PREFERENCES

class DistancePreference(Preference):
    def __init__(self, weight, readable=None):
        self.weight = weight
        assert self.weight <= 0, \
            "DistancePreference must be negative."
        self.readable = "minimize travel distance" if self.weight != 0 \
            else "don't care about how long the travel distance is"

    @classmethod
    def generate(cls, game_data):
        return [cls(-random_pref_pos(), None)]

    def score(self, itinerary):
        evt_scores = []
        for evt in itinerary:
            if evt is None or evt["type"] != "travel":
                evt_scores.append(0)
                continue
            evt_scores.append(int(self.weight * float(evt["data"])))
        return sum(evt_scores), evt_scores

class PriceBudgetPreference(Preference):
    def __init__(self, weight, budget, readable=None):
        self.weight = weight
        self.budget = budget
        assert self.weight <= 0, \
            "PriceBudget preference must be negative."
        self.readable = f"keep budget below ${budget}"

    @classmethod
    def generate(cls, game_data):
        return [cls(-random_pref_pos(), random.choice(range(30, 100, 10)), None)]

    def score(self, itinerary):
        price = sum([
            e["est_price"] for e in itinerary if e and "est_price" in e])
        score = self.weight if price > self.budget else 0
        return score, None

## FEATURE PREFERENCES

class FeaturePreference(Preference):
    def __init__(self, name, weight, value_sets, readable):
        self.name = name
        self.weight = weight
        # [bad_vals, good_vals]
        self.value_sets = value_sets
        self.readable = readable

    @classmethod
    def generate(cls, game_data):
        """Generate a set of feature preferences for a game."""
        prefs = []
        for feat, pref_info in game_data["preferences"].items():
            if np.random.random() < .5: continue
            if pref_info["generate"] == "any_k":
                info = game_data["features"][feat]
                vals = random.sample(
                    info["values"],
                    k=rand_size(info["values"]) + 1
                )
                num_neg = rand_size(vals)
                descs = []
                if num_neg > 0:
                    dislikes = ", ".join(vals[:num_neg])
                    descs.append(f"don't like: {dislikes}")
                if num_neg < len(vals):
                    likes = ", ".join(vals[num_neg:])
                    descs.append(f"like: {likes}")
                descs = ", ".join(descs)
                prefs.append(cls(
                    feat, random_pref_pos(),
                    [vals[:num_neg], vals[num_neg:]],
                    descs
                ))
            elif pref_info["generate"] == "any_1":
                info = game_data["features"][feat]
                val = random.choice(info["values"])
                if np.random.random() < .5:
                    prefs.append(cls(
                        feat, random_pref_pos(),
                        [[val], []],
                        f"don't like {val} places"))
                else:
                    prefs.append(cls(
                        feat, random_pref_pos(),
                        [[], [val]],
                        f"like {val} places"))
            else:
                my_pref = random.choice(pref_info["prefs"])
                prefs.append(cls(
                    feat, random_pref_pos(), my_pref["value_sets"],
                    my_pref["description"],
                ))
        return prefs

    def score(self, itinerary):
        evt_scores = []
        for evt in itinerary:
            if evt is None or evt["type"] != "event" or \
                    self.name not in evt["features"]:
                evt_scores.append(0)
                continue
            evt_feat = evt["features"][self.name]
            if evt_feat in self.value_sets[0]:
                evt_scores.append(-self.weight)
            elif evt_feat in self.value_sets[1]:
                evt_scores.append(self.weight)
            else:
                evt_scores.append(0)
        return sum(evt_scores), evt_scores


ALL_PREFS = [
    FeaturePreference,
    PriceBudgetPreference,
    WantToGo,
    AtLeastOneEventType
]
PREF_NAME_TO_CLS = {
    "FeaturePreference": FeaturePreference,
    "PriceBudgetPreference": PriceBudgetPreference,
    "WantToGo": WantToGo,
    "AtLeastOneEventType": AtLeastOneEventType,
    # not included in ALL_PREFS bc always included in a game
    "DistancePreference": DistancePreference,
}
ALL_CONSTRAINTS = [
    MaxN,
#    DistanceBudget
]

if __name__ == "__main__":
    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    dataf = f"static/travel_data.yaml"
    game_data = yaml.load(open(dataf, "r"))
    print(WantToGo.generate(game_data))



