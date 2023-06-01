import json
import openai
import os
import pathlib
from rich.prompt import IntPrompt, Prompt
from rich.markup import escape

from envs import DialogueEnv
from utils import num_tokens

try:
    with open(pathlib.Path(__file__).parent / ".api_key") as f:
        x = json.load(f)
        openai.organization = x["organization"]
        openai.api_key = x["api_key"]
    print("Loaded .api_key")
except:
    openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    print("Warning: no OpenAI API key loaded.")

class OutOfContextError(Exception):
    pass

class DryRunPlayer:

    def __init__(self, prompt, role, console, task="planning"):
        self.prompt = prompt
        self.role = role
        self.console = console
        self.calls = 0
        self.task = task

    def observe(self, obs):
        self.prompt += obs

    def respond(self):
        self.calls += 1
        if self.role == "agent" and self.calls == 5:
            if self.task == "planning":
                return f" [propose] [Saul's, Cookies Cream, Mad Seoul]"
            elif self.task == "mediation":
                return f" [propose] User 0: [1], User 1: [15]"
        elif self.role == "user" and self.calls == 6:
            return f" [reject]"
        return f" [message] {self.calls}"

class LLMPlayer:

    def __init__(self, prompt, role, console, model_kwargs=None,
                 prefix="\nYou:", optional=None):
        self.prompt = prompt
        self.role = role
        self.console = console
        self.model = "text-davinci-003"
        self.optional = optional
        self.removed_optional = False
        if self.role in ["user", "agent", "user0", "user1"]:
            stop_tokens = ["User", "Agent", "You", "\n"]
        elif self.role in ["player-1", "player-2"]:
            stop_tokens = ["Partner", "You", "\n"]
        else:
            raise NotImplementedError
        self.model_kwargs = dict(
            model=self.model,
            temperature=0.1,
            top_p=.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=stop_tokens,
        )
        if model_kwargs is not None:
            self.model_kwargs.update(**model_kwargs)
        self.prefix = prefix
    #    self.model = "gpt-3.5-turbo"

    def observe(self, obs):
        self.prompt += obs

    def respond(self):
        self.console.rule(f"{self.role}'s turn")
        if not self.prompt.endswith(self.prefix):
            self.prompt += self.prefix
        #self.console.print(escape(self.prompt))
        remaining = 4096 - num_tokens(self.prompt)
        if remaining < 0 and self.optional:
            self._remove_optional_context()
            remaining = 4096 - num_tokens(self.prompt)
        # Still out of context after removing
        if remaining < 0:
            print("OUT OF CONTEXT! Remaining ", remaining)
            raise OutOfContextError()
        kwargs = dict(
            prompt=self.prompt,
            max_tokens=min(remaining, 128),
        )
        kwargs.update(**self.model_kwargs)
        response = openai.Completion.create(**kwargs)
        self.console.print("Response: ",
                           escape(response["choices"][0]["text"].strip()))
        self.console.print("stop: ", response["choices"][0]["finish_reason"])
        if response["choices"][0]["finish_reason"] == "length":
            if not self.optional:
                raise OutOfContextError()
            self._remove_optional_context()
            response = openai.Completion.create(**kwargs)
            self.console.print("Response: ",
                               escape(response["choices"][0]["text"].strip()))
            self.console.print("stop: ", response["choices"][0]["finish_reason"])
        self.console.print(response["usage"])
        return response["choices"][0]["text"].strip()

    def _remove_optional_context(self):
        print("Cutting out optional context from prompt.")
        if self.removed_optional:
            print("!! already removed.")
            return
        self.prompt = (
            self.prompt[:self.prompt.index(self.optional)] +
            self.prompt[self.prompt.index(self.optional) + len(self.optional):])
        self.removed_optional = True

class HumanPlayer:

    def __init__(self, prompt, role, console, prefix="\nYou:"):
        self.prompt = prompt
        self.role = role
        self.console = console
        self.prefix = prefix

    def observe(self, obs):
        self.prompt += obs

    def respond(self):
        if not self.prompt.endswith(self.prefix):
            self.prompt += self.prefix
        self.console.rule(f"Your turn ({self.role})")
        self.console.print(escape(self.prompt))
        resp = ""
        if self.prefix.strip().endswith("You to"):
            id_ = Prompt.ask(
                escape(f"Choose a player to talk to"),
                choices=["0","1","all"])
            resp += f" {id_}:"
        mtypes = ["[message]", "[propose]", "[accept]", "[reject]"]
        choices = " ".join(
                [f"({i}): {type_}" for i, type_ in enumerate(mtypes)])
        type_ = IntPrompt.ask(
                escape(
                    f"Choose one of the following message types:"
                    f"\n{choices}"),
                choices=["0","1","2","3"])
        message_type = mtypes[type_]
        if message_type not in ("[accept]", "[reject]"):
            content = Prompt.ask(escape(f"{message_type}"))
        else:
            content = ""
        resp += f" {message_type} {content}"
        return resp
