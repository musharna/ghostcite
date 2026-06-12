"""Semantic backends for claim-support checking.

A backend takes a (claim, source_text) pair and returns a SupportResult.
Built-ins are thin HTTP adapters over the existing httpx dep:
  - OpenAICompatibleBackend: any OpenAI-compatible /chat/completions endpoint
    (Ollama, vLLM, LM Studio, llama.cpp server, OpenAI, Together, ...).
  - AnthropicBackend: the Anthropic Messages API.
Both use temperature=0 to maximize reproducibility (NOT guaranteed deterministic;
findings built from these are flagged deterministic=False upstream).
"""

from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

import httpx

from ghostcite.models import SemanticVerdict, SupportResult

_TIMEOUT = 30.0

_SYSTEM = (
    "You are a citation claim-support checker. Given a CLAIM and the ABSTRACT of "
    "the cited source, decide whether the abstract supports the claim. Respond with "
    'ONLY a JSON object: {"verdict": "supported"|"unsupported"|"uncertain", '
    '"rationale": "<one sentence>"}. Use "uncertain" when the abstract lacks enough '
    "information to judge. Do not output anything except the JSON object."
)


def _user_prompt(claim: str, source_text: str) -> str:
    return f"CLAIM:\n{claim}\n\nABSTRACT:\n{source_text}"


def _parse_verdict(content: str, backend_name: str) -> SupportResult:
    """Parse a backend's text response into a SupportResult, tolerating fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
        verdict = SemanticVerdict(str(obj["verdict"]).lower())
        rationale = str(obj.get("rationale", ""))
    except (ValueError, KeyError, TypeError) as e:
        raise SemanticBackendError(f"unparseable backend response: {content!r}") from e
    return SupportResult(verdict=verdict, rationale=rationale, backend=backend_name)


class SemanticBackendError(RuntimeError):
    """Raised on backend transport or response-parsing failure."""


@runtime_checkable
class SemanticBackend(Protocol):
    name: str

    def assess_support(self, claim: str, source_text: str) -> SupportResult: ...


class OpenAICompatibleBackend:
    def __init__(self, *, base_url: str, api_key: str | None, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = f"openai:{model}"

    def assess_support(self, claim: str, source_text: str) -> SupportResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _user_prompt(claim, source_text)},
            ],
        }
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise SemanticBackendError(f"{self.name} request failed: {e}") from e
        return _parse_verdict(content, self.name)


class AnthropicBackend:
    _URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.name = f"anthropic:{model}"

    def assess_support(self, claim: str, source_text: str) -> SupportResult:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 256,
            "temperature": 0,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": _user_prompt(claim, source_text)}],
        }
        try:
            r = httpx.post(self._URL, headers=headers, json=body, timeout=_TIMEOUT)
            r.raise_for_status()
            content = r.json()["content"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise SemanticBackendError(f"{self.name} request failed: {e}") from e
        return _parse_verdict(content, self.name)


def build_backend(
    kind: str, *, base_url: str | None, api_key: str | None, model: str
) -> SemanticBackend:
    """Construct a built-in backend by kind, validating required config."""
    if kind == "openai":
        if not base_url:
            raise SemanticBackendError(
                "openai backend needs a base URL (--semantic-base-url or "
                "GHOSTCITE_SEMANTIC_BASE_URL), e.g. http://localhost:11434/v1"
            )
        return OpenAICompatibleBackend(base_url=base_url, api_key=api_key, model=model)
    if kind == "anthropic":
        if not api_key:
            raise SemanticBackendError(
                "anthropic backend needs an API key (--semantic-api-key or "
                "GHOSTCITE_SEMANTIC_API_KEY)"
            )
        return AnthropicBackend(api_key=api_key, model=model)
    raise SemanticBackendError(f"unknown semantic backend: {kind!r} (choices: openai, anthropic)")
