from typing import Literal
from rich import print
from rich.console import Console
import tyro
from dialop.envs import (
    OptimizationEnv, PlanningEnv, MediationEnv
    )
from dialop.players import HumanPlayer
from dialop.utils import run, run_multiagent

def main(
    game: Literal["optimization", "planning", "mediation"],
    max_length: int = 30,
    ):
    console = Console()
    if game == "optimization":
      env = OptimizationEnv()
    elif game == "planning":
      env = PlanningEnv()
    else:
      env = MediationEnv()

    players = {
        p: HumanPlayer(env.instructions[i], p, console)
        for i, p in enumerate(env.players)
    }

    if game == "mediation":
        players["agent"].prefix = "\nYou to"
        run_multiagent(console, env, players, max_length)
    else:
        run(console, env, players, max_length)


tyro.cli(main)
