import itertools
import random
import time
from typing import List, Tuple

import numpy as np
import scipy
from dialop.games.base_game import DialogueGame

# Maximum number of tables to generate:
MAX_TABLES = 10000

TASKS = [
    "BLEU: a Method for Automatic Evaluation of MT",
    "Electra: Pre-training Text Encoders as Discriminators",
    "GloVe: Global Vectors for Word Representation",
    "GLUE: A Multi-Task Benchmark and Analysis Platform for NLU",
    "LLaMA: Open and Efficient Foundation Language Models",
    "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
    "QuAC: Question Answering in Context",
    "SWAG: An Adversarial Dataset for Commonsense Inference",
]

TASKS_SHORT = [task.split(":")[0] for task in TASKS]

WORKERS = [
    "Ava Li",
    "Daniel Nguyen",
    "Sofia Patel",
    "Andrei Petrov",
    "Morgan Reed",
    "Joseph Santos",
    "Ethan Smith",
    "Noah Wilson"
]

class Table:
    """
    Bipartite matching table for reviewer-matching scenario

    Attributes:
      - num_rows: number of rows (reviewers)
      - num_cols: number of columns (papers)
      - values: a 2D numpy array of costs
    """
    def __init__(self, num_rows=None, num_cols=None, values=None, max_val=100, empty_val=-1):
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.max_val = max_val
        self.empty_val = empty_val
        self.current_proposal = None
        if values is not None:
            self.values = values
            self.num_rows, self.num_cols = self.values.shape
        else:
            assert num_rows and num_cols, \
                ("num_rows and num_cols must be defined unless initializing from "
                "values.")
            self.num_rows = num_rows
            self.num_cols = num_cols
            self.values = np.zeros((num_rows, num_cols))
            self.randomize()
        if self.num_rows != self.num_cols:
          raise NotImplementedError("Only bipartite matchings are supported.")

    def randomize(self):
        self.values = np.random.randint(0, self.max_val, (self.num_rows, self.num_cols))

    def set_values(self, values):
        self.values = values

    def find_max_value_known_assignment(self, knowns) -> Tuple[List, float]:
        """Find the max value assignment given a set of views (if the
        players pool their knowledge, what is the best they can do?).

        Args:
            knowns (List[np.ndarray]): list of player view mask arrays
        Returns:
            assignment (List[Tuple]): list of tuples (reviewer idx, paper idx)
                representing the best assignment
            score (float): score of the best assignment
        """
        known = np.logical_or(*knowns)
        pooled_expected_table = -self.values * known - self.max_val/2 * (1-known)
        rows, cols = scipy.optimize.linear_sum_assignment(pooled_expected_table)
        assignment = list(zip(rows, cols))
        score = self.score(assignment)
        return assignment, score

    def get_random_view(self, p_cell_observed):
        """Returns a new Table instance representing a view of this table."""
        unknown = np.random.choice(2, self.values.shape, p=[p_cell_observed,
          1.0 - p_cell_observed])
        output_values = np.ma.masked_array(self.values, mask=unknown)
        output_values = np.ma.filled(output_values, self.empty_val)
        output_table = Table(values=output_values)
        return output_table, 1 - unknown

    def score(self, assignment: List[Tuple]):
        assert len(assignment) == self.num_rows, \
            f"{len(assignment)} =/= {self.num_rows}"
        return sum([self.values[r][c] for r, c in assignment]).item()


class OptimizationGame(DialogueGame):
    """Tracks game state for the cooperative dialog game."""

    DEFAULT_CONFIG = {
        "num_rows": 8,
        "num_cols": 8,
        "p_cell_observed": 0.4,
        "take_turns": True,
    }
    def __init__(self, env_config):
        self.TASKS = TASKS
        self.WORKERS = WORKERS
        config = OptimizationGame.DEFAULT_CONFIG.copy()
        config.update(env_config)
        self.num_rows = config["num_rows"]
        self.num_cols = config["num_cols"]
        assert self.num_rows == self.num_cols
        self.p_cell_observed = config["p_cell_observed"]
        self.take_turns = config["take_turns"]

    @classmethod
    def create_from_game_state(cls, game_state):
        """
        Creates a game from an offline game state.
        Only instantiates the state needed to score proposals.
        """
        game = cls({})
        game.reset(randomize=False)
        mask1 = np.array(game_state["mask1"])
        mask2 = np.array(game_state["mask2"])
        game.scales = [game_state["scale1"], game_state["scale2"]]
        table = game_state["table"]
        num_rows, num_cols = len(table), len(table[0])
        game.table = Table(num_rows, num_cols)
        game.table.values = np.array(table)
        game.masks = [mask1, mask2]
        game.tables = [
            game._preprocess_table(game.table, game.masks[0], game.scales[0]),
            game._preprocess_table(game.table, game.masks[1], game.scales[1])
        ]
        game.num_rows = num_rows
        game.num_cols = num_cols
        if len(game.action_log) > 0:
            last_player = game.action_log[-1]["player"]
            game.turn_player = 1 - last_player
        game.best_assignment_reward = game_state["best_assignment_reward"]
        # Just for UI display
        game.best_assignment = None
        game.combined_tables = None
        return game

    def reset(self, randomize=True):
        """Regenerates a new game table and returns initial observations
        for each player."""
        self.start_time = time.time()
        self.action_log = []
        self.message_history = []
        self.turn_player = 0 if self.take_turns else None
        self.proposal = None
        self.is_full_proposal = False
        self.proposal_reward = 0
        self.best_assignment_reward = 0

        counter = 0
        while True and randomize:
            self.table = Table(self.num_rows, self.num_cols)
            view1, known1 = self.table.get_random_view(self.p_cell_observed)
            view2, known2 = self.table.get_random_view(self.p_cell_observed)
            scale1, scale2 = random.uniform(1,10), random.uniform(1,10)
            self.scales = [scale1, scale2]
            self.masks = [known1, known2]
            # If neither player knows a value, set it to the mean:
            self.table.values[np.logical_not(known1) & np.logical_not(known2)] = self.table.max_val / 2

            self.best_assignment, self.best_assignment_reward = self.table.find_max_value_known_assignment([
              known1, known2])

            # Filter to find hard problems:
            assign1, rew1 = self.table.find_max_value_known_assignment([known1, known1])
            assign2, rew2 = self.table.find_max_value_known_assignment([known2, known2])
            if (rew1 * 1.25 < self.best_assignment_reward) \
                and (rew2 * 1.25 < self.best_assignment_reward) \
                or counter > MAX_TABLES:
                table1 = self._preprocess_table(view1, known1, scale1)
                table2 = self._preprocess_table(view2, known2, scale2)
                self.tables = [table1, table2]

                # Compute combined table:
                combined_knowns = np.logical_or(*self.masks)
                combined_table1 = self._preprocess_table(self.table, combined_knowns, scale1)
                combined_table2 = self._preprocess_table(self.table, combined_knowns, scale2)
                self.combined_tables = [combined_table1, combined_table2]
                obs0 = {
                    "table": table1,
                    "scale": scale1,
                    "max_reward": self.best_assignment_reward
                }
                obs1 = {
                    "table": table2,
                    "scale": scale2,
                    "max_reward": self.best_assignment_reward
                }
                return obs0, obs1
            counter += 1

    def message(self, message, metadata=None):
        metadata = metadata or {}
        self.message_history.append(message)
        self.action_log.append({
            **metadata,
            "type": "message",
            "message": message,
            "player": message["from_player"],
            "time": time.time() - self.start_time
        })
        self._take_turn()

    @property
    def proposal_readable(self):
        if not self.proposal:
            return "Proposal: None"
        # Sort proposal by paper title:
        sorted_proposal = sorted(self.proposal, key=lambda x: TASKS_SHORT[x[1]])
        proposal_str = "<br/>".join([f"&emsp; - {TASKS_SHORT[paper_id]}: {WORKERS[reviewer_id]}" for reviewer_id,
                                     paper_id in sorted_proposal])
        proposal_str = "Proposal:<br/>" + proposal_str
        return proposal_str

    def propose(self, proposal, from_player, proposal_ids=None, metadata=None):
        metadata = metadata or {}
        # Parse proposal
        # Proposal format: '[{"name":"paper-0","value":"Chris Manning"},{"name":"paper-1","value":"Jason Eisner"}]'
        if proposal_ids is not None:
            parsed = proposal_ids
            self.proposal_cell_ids = proposal_ids
        else:
            self.proposal_cell_ids = proposal["cells"]
            parsed = []
            for assignment in proposal["assignments"]:
                paper_id = int(assignment["name"].split("-")[1])
                reviewer_id = WORKERS.index(assignment["value"])
                parsed.append((reviewer_id, paper_id))
        # Sort alphabetically by person name:
        parsed = sorted(parsed, key=lambda x: WORKERS[x[0]])
        self.proposal = parsed
        self.is_full_proposal = len(self.proposal_cell_ids) == self.num_rows
        self._take_turn()
        self.action_log.append({
            **metadata,
            "type": "proposal",
            "proposal": self.proposal_readable,
            "proposal_ids": parsed,
            "player": from_player,
            "time": time.time() - self.start_time
        })
        return {"proposal_data": proposal}

    def proposal_response(self, response, from_player, metadata=None):
        metadata = metadata or {}
        if response["accept"]:
            game_over = self.is_full_proposal
            proposal_reward = self.table.score(self.proposal)
        else:
            game_over = False
            self.proposal = None
            self.is_full_proposal = False
            proposal_reward = 0
        self.action_log.append({
            **metadata,
            "type": "proposal_response",
            "response": response,
            "player": from_player,
            "time": time.time() - self.start_time
        })
        self.proposal_reward = proposal_reward
        infos = [{
            "your_reward": proposal_reward,
            "best_reward": self.best_assignment_reward,
            "scale": self.scales[i],
            "proposal": self.proposal_cell_ids,
            "best_proposal": self._process_best_proposal(self.best_assignment) if \
                self.best_assignment else None,
            "player_table": self.tables[i],
            "combined_table": self.combined_tables[i] if \
                self.combined_tables else None,
        } for i in range(2)]
        return game_over, infos

    def get_game_info(self):
        return {
            "table": self.table.values.tolist(),
            "mask1": self.masks[0].tolist(),
            "mask2": self.masks[1].tolist(),
            "scale1": self.scales[0],
            "scale2": self.scales[1],
            "action_log": self.action_log,
            "proposal_reward": self.proposal_reward,
            "best_assignment_reward": self.best_assignment_reward,
            "start_time": self.start_time
        }

    def _compute_all_solutions(self):
        scores = []
        for reviewers in itertools.permutations(range(self.num_rows)):
            assignment = list(zip(reviewers, range(self.num_cols)))
            scores.append(self.table.score(assignment))
        return scores

    def _process_best_proposal(self, proposal):
        cells = []
        for cell in proposal:
            row, col = cell
            id = "cell-" + str(1+row) + "-" + str(1+col);
            cells.append(id)
        return cells

    def _take_turn(self):
        if self.take_turns:
            self.turn_player = 1 - self.turn_player

    def _preprocess_table(self, table: Table, known: np.ndarray, scaling_factor: float) -> List[List]:
        assert table.values.shape == (self.num_rows, self.num_cols)
        table = table.values.tolist()
        # Replace empty vals with empty string for display
        for i in range(self.num_rows):
            for j in range(self.num_cols):
                if not known[i][j]:
                    table[i][j] = ""
                else:
                    table[i][j] = int(table[i][j] * scaling_factor)
        # Add row headers
        for i in range(len(table)):
            table[i] = [WORKERS[i], *table[i]]
        # Add col headers
        table = [["", *TASKS[:self.num_cols]]] + table
        return table

