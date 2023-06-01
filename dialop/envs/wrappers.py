class WordLimit:

    def __init__(self, env, players):
        self.env = env
        self.players = players

    def __getattr__(self, attr):
        return getattr(self.env, attr)

    def reset(self, word_limit, game_state=None):
        obs = self.env.reset(game_state)
        assert word_limit > 0
        self.word_limit = word_limit
        self.words_left = word_limit
        self.end_soon = False
        self.proposal_made = False
        for msg in self.game.action_log:
            if msg["type"] == "message":
                self.words_left -= len(msg["message"]["data"].split(" "))
        if obs["turn_player"] in self.players:
            obs[obs["turn_player"]] = self._insert_word_limit(
                obs[obs["turn_player"]])
        return obs

    def step(self, message):
        obss, resample = self.env.step(message)
        if "[message]" in message:
            text = message[message.index("] ") + 2:]
            self.words_left -= len(text.split(" "))
        if self.end_soon:
            if self.proposal_made and obss["turn_player"] not in self.players:
                # Accept automatically
                obss, resample = self.env.step(" [accept]")
                if not obss["done"]:
                    import pdb; pdb.set_trace()
                obss["info"]["word_limited"] = True
                return obss, resample

            if "[propose]" in message:
                self.proposal_made = self.game.is_full_proposal
        if obss["turn_player"] not in self.players:
            return obss, resample
        ob = obss[obss["turn_player"]]
        obss[obss["turn_player"]] = self._insert_word_limit(ob)
        return obss, resample

    def _insert_word_limit(self, ob):
        ob = ob.rsplit("\n", 1)
        msg = f"Words left: {self.words_left}"
        if self.words_left < 25:
            msg += "\nYou must make your best final proposal now."
            self.end_soon = True
        ob = f"{ob[0]}\n{msg}\n{ob[1]}"
        return ob


class ForceProposal:
    def __init__(self, env, players):
        self.env = env
        self.players = players

    def __getattr__(self, attr):
        return getattr(self.env, attr)

    def reset(self, word_limit, game_state=None):
        obs = self.env.reset(game_state)
        assert word_limit > 0
        self.word_limit = word_limit
        self.words_left = word_limit
        self.end_soon = False
        self.proposal_made = False
        for msg in self.game.action_log:
            if msg["type"] == "message":
                self.words_left -= len(msg["message"]["data"].split(" "))
        if obs["turn_player"] in self.players:
            obs[obs["turn_player"]] = self._insert_word_limit(
                obs[obs["turn_player"]])
        return obs

    def step(self, message):
        obss, resample = self.env.step(message)
        if "[message]" in message:
            text = message[message.index("] ") + 2:]
            self.words_left -= len(text.split(" "))
        if self.end_soon:
            if self.proposal_made: # and obss["turn_player"] not in self.players:
                # Accept automatically
                obss, resample = self.env.step(" [accept]")
                if not obss["done"]:
                    import pdb; pdb.set_trace()
                obss["info"]["word_limited"] = True
                return obss, resample

            if "[propose]" in message:
                self.proposal_made = True # self.game.is_full_proposal
            # elif self.proposal_made and "[accept]" not in message:
            #     raise self.env.game_error("Agent must [accept] the proposal")
            # else:
            #     raise self.env.game_error("Agent must send a message beginning with [propose]")
        # if obss["turn_player"] not in self.players:
        #     return obss, resample
        ob = obss[obss["turn_player"]]
        obss[obss["turn_player"]] = self._insert_word_limit(ob)
        return obss, resample

    def _insert_word_limit(self, ob):
        ob = ob.rsplit("\n", 1)
        # msg = f"Words left: {self.words_left}"
        msg = ""
        if self.words_left < 25:
            msg += "\nYou must make your best final proposal now."
            self.end_soon = True
        ob = f"{ob[0]}\n{msg}\n{ob[1]}"
        return ob

class AsymmetricForceProposal:
    def __init__(self, env, players):
        self.env = env
        self.players = players

    def __getattr__(self, attr):
        return getattr(self.env, attr)

    def reset(self, word_limit, game_state=None):
        obs = self.env.reset(game_state)
        assert word_limit > 0
        self.word_limit = word_limit
        self.words_left = word_limit
        self.end_soon = False
        self.proposal_made = False
        for msg in self.game.action_log:
            if msg["type"] == "message":
                self.words_left -= len(msg["message"]["data"].split(" "))
        if obs["turn_player"] in self.players:
            obs[obs["turn_player"]] = self._insert_word_limit(
                obs[obs["turn_player"]])
        return obs

    def step(self, message):
        obss, resample = self.env.step(message)
        if "[message]" in message:
            text = message[message.index("] ") + 2:]
            self.words_left -= len(text.split(" "))
        if self.end_soon:
            if self.proposal_made and obss["turn_player"] not in self.players:
                # Accept automatically
                obss, resample = self.env.step(" [accept]")
                if not obss["done"]:
                    import pdb; pdb.set_trace()
                obss["info"]["word_limited"] = True
                return obss, resample

            if "[propose]" in message:
                self.proposal_made = self.game.is_full_proposal
            # elif self.proposal_made and "[accept]" not in message:
            #     raise self.env.game_error("Agent must [accept] the proposal")
            # else:
            #     raise self.env.game_error("Agent must send a message beginning with [propose]")
        if obss["turn_player"] not in self.players:
            return obss, resample
        ob = obss[obss["turn_player"]]
        obss[obss["turn_player"]] = self._insert_word_limit(ob)
        return obss, resample

    def _insert_word_limit(self, ob):
        ob = ob.rsplit("\n", 1)
        # msg = f"Words left: {self.words_left}"
        msg = ""
        if self.words_left < 25:
            msg += "\nYou must make your best final proposal now."
            self.end_soon = True
        ob = f"{ob[0]}\n{msg}\n{ob[1]}"
        return ob