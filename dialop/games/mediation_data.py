from datetime import datetime, timedelta
from dateutil.parser import parse
import random
import numpy as np
from collections import namedtuple

START = datetime(2023, 5, 31, 9)
END = datetime(2023, 6, 2, 19)

Flight = namedtuple("Flight", ["date", "start_time", "end_time", "price"])

def datetime_range(start, end, delta, min_hour=None, max_hour=None):
    current = start
    while current < end:
        if (not min_hour or current.hour >= min_hour) and \
            (not max_hour or current.hour <= max_hour):
            yield current
        current += delta

def random_datetime(start, end):
    delta = end - start
    mins_delta = (delta.days * 24 * 60) + delta.seconds // 60
    random_min = random.randrange(mins_delta)
    return start + timedelta(minutes=random_min)

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")

def hr_min(delta):
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours} hr {minutes} min"

def hr_delta(delta):
    return delta.days * 24 + delta.seconds // (3600)

def times_overlap(range1, range2):
    start1, end1 = range1
    start2, end2 = range2
    if start1 < start2 < end1:
        return True
    if start2 < start1 < end2:
        return True
    return False


class Calendar:

    def __init__(self, p_event):
        self.p_event = p_event
        self._generate()

    def _event_start_times(self):
        """Generate all possible start times in the date range."""
        return datetime_range(
            START,
            END,
            timedelta(minutes=30),
            min_hour=9,
            max_hour=20,
        )

    def _generate(self):
        events = []
        last_start = START
        for time in self._event_start_times():
            if time < last_start:
                continue
            if np.random.random() < self.p_event:
                length = random.choice([30, 60, 120, 240])
                events.append({
                    "id": len(events),
                    "title": "", #len(events),
                    "start": iso(time),
                    "end": iso(time + timedelta(minutes=length)),
                    "importance": random.randint(1, 10)
                })
                last_start = time + timedelta(minutes=length)
        self.events = events

class FlightSet:

    def __init__(self, city_name, num_flights):
        self.name = city_name
        self.num_flights = num_flights
        # Average duration for a flight to ensure all flights
        #  in this set take around the same time
        self.mean_duration_m = 60 * random.randint(1, 10)
        self.mean_price = random.randrange(50, 1000)
        self._generate()

    def _generate(self):
        flights = []
        for _ in range(self.num_flights):
            start = random_datetime(START, END)
            duration = timedelta(
                minutes=self.mean_duration_m + np.random.exponential())
            flights.append({
                "id": len(flights),
                "carrier": random.choice(["JetBlue", "American", "Delta",
                                          "Southwest", "United", "Alaska"]),
                "date": str(start.date()),
                "start": iso(start),
                "end": iso(start + duration),
                "duration": hr_min(duration),
                "price": max(50, round(
                    np.random.normal(loc=self.mean_price,
                                     scale=self.mean_price)
                ))
            })
        self.flights = sorted(flights, key=lambda x: x["end"])


if __name__ == "__main__":
    f = FlightSet("non", 2)
    f._generate()
    print(f.flights)
    import pdb; pdb.set_trace()
#    c = Calendar(0.1)
#    print("\n".join([str(e) for e in c.events]))
