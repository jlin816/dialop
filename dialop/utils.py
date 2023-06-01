from collections import defaultdict
import openai
import re
import tiktoken
import time
from dateutil.parser import parse
from pathlib import Path
from itertools import cycle

enc = tiktoken.get_encoding("cl100k_base")
SEP = "=" * 20
SEP1 = "-" * 20

def run(console, env, players, max_length=30):
    obss = env.reset()
    for t in range(max_length):
      console.rule("environment obs")
      console.print(obss)
      [player.observe(obss[pname]) for pname, player in players.items()]
      resp = players[obss["turn_player"]].respond()
      obss, resample = env.step(resp)
      if obss["done"]:
        break
    print(obss)

def run_multiagent(console, env, players, max_length=45):
    player_cycle = cycle(players.keys())
    obss = env.reset()
    for t in range(max_length):
        console.rule("environment obs")
        console.print(obss)
        [player.observe(obss[pname]) for pname, player in players.items()]
        # Cycle through players, letting them speak if it's their turn
        next_player = next(player_cycle)
        while next_player not in obss["turn_players"]:
            next_player = next(player_cycle)
        resp = players[next_player].respond()
        obss, resample = env.step(resp, next_player)
        if obss["done"]:
            break
    print(obss)

def num_tokens(text):
  return len(enc.encode(text))

def count_words(action_log):
    count = 0
    for msg in action_log:
        if msg["type"] == "message":
            count += len(msg["message"]["data"].split(" "))
    return count

def retry(max_attempts=3, delay=60, allowed_exceptions=None):
    if allowed_exceptions is None:
        allowed_exceptions = []

    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if type(e) in allowed_exceptions:
                        print(f"Attempt {attempts+1} failed: {type(e)} {e}")
                        attempts += 1
                        time.sleep(delay)
                    else:
                        raise e
            print(f"Max attempts reached. Giving up.")
        return wrapper
    return decorator

class Logger:

    def __init__(self, logfile):
        self.logfile = logfile
        self.buffer = ""
        self.logs = defaultdict(list)

    def write(self, title="", value=""):
        self.buffer += f"\n\n{SEP} {title} {SEP}\n\n>{value}<"

    def log(self, key, value, title=""):
        self.logs[key].append(f"\n\n{SEP1} {title} {SEP1}\n>{value}")

    def flush(self):
        with open(self.logfile, "a") as f:
            f.write(self.buffer)
        self.buffer = ""

    def flush_key(self, key, title="", joiner=""):
        with open(self.logfile, "a") as f:
            f.write(f"\n\n{SEP} {title} {SEP}\n{joiner.join(self.logs[key])}")
        self.logs[key] = []

    def close(self):
        self.flush()
