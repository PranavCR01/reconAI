"""Scriptable fake for every LLM client the backend calls.

Covers anthropic.Anthropic().messages.create, groq.Groq().chat.completions.create,
langchain_anthropic.ChatAnthropic(...).invoke and langchain_groq.ChatGroq(...).invoke.
Tests script responses by prompt matcher, inject failures, and inspect `calls`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace as NS
from typing import Callable

import httpx

Matcher = str | Callable[[str], bool]
Response = str | Callable[[str, str], str]  # (prompt, model) -> text


def api_status_error(status: int = 529, message: str = "overloaded"):
    import anthropic

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError(message, response=httpx.Response(status, request=request), body=None)


def api_connection_error():
    import anthropic

    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


@dataclass
class _Rule:
    matcher: Matcher
    response: Response | None = None
    error: Exception | None = None
    times: int | None = None  # None = unlimited
    input_tokens: int = 1200
    output_tokens: int = 300

    def hits(self, prompt: str) -> bool:
        if self.times is not None and self.times <= 0:
            return False
        if callable(self.matcher):
            return bool(self.matcher(prompt))
        return self.matcher in prompt


@dataclass
class FakeLLM:
    """Default behavior answers every prompt the pipeline sends; rules override it."""

    synthesis_confidence: float = 0.9
    classification: str = "VALUE_MISMATCH"
    rules: list[_Rule] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    # -- scripting --------------------------------------------------------
    def respond(self, matcher: Matcher, response: Response, *, times: int | None = None,
                input_tokens: int = 1200, output_tokens: int = 300) -> None:
        self.rules.insert(0, _Rule(matcher, response=response, times=times,
                                   input_tokens=input_tokens, output_tokens=output_tokens))

    def fail(self, matcher: Matcher, error: Exception | None = None, *, times: int | None = None) -> None:
        self.rules.insert(0, _Rule(matcher, error=error or api_status_error(), times=times))

    def calls_matching(self, needle: str) -> list[dict]:
        return [c for c in self.calls if needle in c["prompt"]]

    # -- core -------------------------------------------------------------
    def complete(self, prompt: str, model: str, client: str) -> tuple[str, int, int]:
        for rule in self.rules:
            if rule.hits(prompt):
                if rule.times is not None:
                    rule.times -= 1
                if rule.error is not None:
                    self.calls.append({"model": model, "client": client, "prompt": prompt, "error": type(rule.error).__name__})
                    raise rule.error
                text = rule.response(prompt, model) if callable(rule.response) else rule.response
                self.calls.append({"model": model, "client": client, "prompt": prompt, "text": text,
                                   "input_tokens": rule.input_tokens, "output_tokens": rule.output_tokens})
                return text, rule.input_tokens, rule.output_tokens
        text, i, o = self._default(prompt)
        self.calls.append({"model": model, "client": client, "prompt": prompt, "text": text,
                           "input_tokens": i, "output_tokens": o})
        return text, i, o

    def _default(self, prompt: str) -> tuple[str, int, int]:
        if "Rank these past incidents" in prompt:
            n = len(re.findall(r"^\[\d+\]", prompt, re.M))
            return json.dumps(list(range(n))), 300, 8
        if "Reply with exactly one of" in prompt:
            return self.classification, 80, 3
        record = re.search(r"\b(00[0-9A-Za-z]{13,16}|a0[0-9A-Za-z]{13,16})\b", prompt)
        rid = record.group(1) if record else "unknown-record"
        return json.dumps({
            "root_cause": f"Root cause for record {rid} established from the collected evidence.",
            "confidence": self.synthesis_confidence,
            "suggested_fix": f"Apply the fix and backfill record {rid}.",
            "postmortem_draft": f"Postmortem for record {rid}.",
            "jira_summary": f"RCA {rid}",
        }), 1500, 400

    # -- client shims -----------------------------------------------------
    def anthropic_client(self, *args, **kwargs):
        fake = self

        class _Messages:
            def create(self, model, max_tokens, messages, **kw):
                text, i, o = fake.complete(messages[-1]["content"], model, "anthropic")
                return NS(content=[NS(type="text", text=text)], usage=NS(input_tokens=i, output_tokens=o),
                          model=model, stop_reason="end_turn")

        return NS(messages=_Messages())

    def groq_client(self, *args, **kwargs):
        fake = self

        class _Completions:
            def create(self, model, messages, max_tokens=None, **kw):
                text, i, o = fake.complete(messages[-1]["content"], model, "groq")
                return NS(choices=[NS(message=NS(content=text))], usage=NS(prompt_tokens=i, completion_tokens=o))

        return NS(chat=NS(completions=_Completions()))

    def chat_model_class(self, client_name: str):
        fake = self

        class _ChatModel:
            def __init__(self, model=None, **kwargs):
                self.model = model or "chat-model"

            def invoke(self, messages):
                text, i, o = fake.complete(messages[-1].content, self.model, client_name)
                return NS(content=text, usage_metadata={"input_tokens": i, "output_tokens": o})

        return _ChatModel
