from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional

class DialogueGame(ABC):
    def __init__(self):
        self.action_log = []
        self.turn_player = 0

    def _take_turn(self):
        self.turn_player = 1 - self.turn_player

    @abstractmethod
    def reset(self) -> Tuple[Dict, Dict]:
        """Reset game state and create a new (randomized) instance
        and return an obs dict for each player."""
        pass

    @abstractmethod
    def message(self, message: str, metadata: Optional[Dict]):
        """Register a dialogue message from a player.
        `metadata` will be saved with this message in the game logs.
        """
        pass

    @abstractmethod
    def propose(self, proposal: Dict, from_player: int, metadata: Optional[Dict]) -> Dict:
        """Update game state with a proposal. Returns obss
        for the receiving player after the proposal."""
        pass

    @abstractmethod
    def proposal_response(self, data: Dict, from_player: int, metadata: Optional[Dict]) -> Tuple:
        """Update game state with a proposal response and returns
        a tuple with the end-of-game information (e.g. reward)."""
        pass

    @abstractmethod
    def get_game_info(self) -> Dict:
        """Return summary of game for logging and saving."""
        pass
