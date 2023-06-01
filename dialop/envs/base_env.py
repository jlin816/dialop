from typing import Optional, Dict
import re

class DialogueEnv:

    def __init__(self):
        ...

    def _parse_message(
            self,
            message: str,
            can_propose: bool,
            can_respond: bool,
            must_respond: bool,
            has_recipient: bool = False,
            ):
        """Parses and checks a message string from a player."""
        if has_recipient:
            m = re.match(
                r"(?P<vroom>0|1|all): \[(?P<mtype>\w+)\](?P<msg>.*)",
                message.strip())
        else:
            m = re.match(
                r"\[(?P<mtype>\w+)\](?P<msg>.*)",
                message.strip())
        if m is None:
            raise GameError(f"Invalid message: {message}."
                            "Messages must be formatted with a type like '[message]"
                            "<content here>'")
        if m["mtype"] == "propose" and not can_propose:
            raise GameError("Your role cannot propose. You can send messages.")
        if (m["mtype"] == "accept" or m["mtype"] == "reject") and not can_respond:
            raise GameError("Your role cannot accept or reject. You can send"
                            " other messages.")
        if m["mtype"] not in ("accept", "reject") and len(m["msg"]) == 0:
            raise GameError("Cannot send empty message.")
        if must_respond and m["mtype"] not in ("accept", "reject"):
            raise GameError("A proposal was made. You must first accept or"
                            " reject it.")
        if has_recipient and m["mtype"] != "propose" and m["vroom"] == "all":
            raise GameError(f"You can only send proposals to everyone. Try"
                            " messaging an individual player.")
        m = {k: v.strip() for k, v in m.groupdict().items()}
        return m

    def reset(self, game_state: Optional[Dict] = None):
        """Resets the environment with new data.

        Will initialize with an existing `game_state` if one is provided.
        Otherwise, will generate a random instance.
        """
        ...

    def step(self, message: str) -> Dict:
        """Steps the env state with a new message.

        Returns:
            dict with observation keys for each player, and `turn_player` for
            the name of the current turn_player
        """
        ...

    def _propose(self, message: str):
        """Register a formal proposal."""
        ...

    def _proposal_response(
            self,
            is_accept: bool,
            from_player: int):
        """Registers a formal acceptance or rejection.
        Args:
            is_accept
            from_player: index of the responding player
        Returns:
            done (bool): whether the game is over
            infos (List[Dict]): game information about the proposal for each
            player
        """
        if self.game.proposal is None or not self.game.is_full_proposal:
            raise GameError(
                "You can only [accept] or [reject] when your partner sends a "
                "full proposal. Either no full proposal has been made yet or "
                "the last proposal has expired. Keep sending more messages."
            )
        done, infos = self.game.proposal_response(
            {"accept": is_accept}, from_player)
        return done, infos

    def _init_from_action_log(self):
        """Constructs the initial observation for each player, potentially
        initializing with a human-human game state and message history.

        Will also update the game state to match the action log, e.g. setting
        proposal state and setting the turn player."""
        ...

class GameError(Exception):
    pass
