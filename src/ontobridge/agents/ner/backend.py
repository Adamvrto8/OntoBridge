from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


def _llm_timeout() -> float:
    """Per-request LLM timeout in seconds (env ONTOBRIDGE_LLM_TIMEOUT, default 60).

    Bounds a single completion call so a hung connection can't freeze the
    pipeline; combined with per-chunk failure isolation in LLMNerExtractor,
    a timed-out chunk is skipped rather than aborting the whole upload.
    """
    try:
        return float(os.environ.get("ONTOBRIDGE_LLM_TIMEOUT", "60"))
    except ValueError:
        return 60.0


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal interface for a text-completion LLM.

    Keeping this to a single method makes swapping backends (Ollama → OpenAI
    → Anthropic) a one-class job with no changes to the extractor.
    """

    def complete(self, system: str, user: str) -> str: ...


class OllamaBackend:
    """LLMBackend backed by a locally running Ollama server.

    Uses ``langchain-ollama`` (already a project dependency) with
    ``temperature=0`` for deterministic, structured output.

    Args:
        model: Any model pulled into your local Ollama instance.
               ``llama3.2`` is a good default — fast, good instruction following.
        base_url: Ollama server URL.  Defaults to the standard local address.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._llm = None  # lazy-loaded on first call

    def complete(self, system: str, user: str) -> str:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ImportError(
                "langchain-ollama is required for OllamaBackend.\n"
                "Install it with:  pip install langchain-ollama langchain-core\n"
                "Or:               pip install 'ontobridge[llm]'"
            ) from exc

        if self._llm is None:
            self._llm = ChatOllama(
                model=self._model,
                base_url=self._base_url,
                temperature=0,
                client_kwargs={"timeout": _llm_timeout()},
            )

        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = self._llm.invoke(messages)
        return str(response.content)


class AnthropicBackend:
    """LLMBackend backed by the Anthropic API (Claude models).

    Reads the API key from the ``ANTHROPIC_API_KEY`` environment variable.
    Set it once in your shell and it will be picked up automatically:

        $env:ANTHROPIC_API_KEY = "sk-ant-..."   # PowerShell
        export ANTHROPIC_API_KEY="sk-ant-..."   # bash/zsh

    Args:
        model: Any Claude model ID. Defaults to claude-haiku-4-5-20251001
               (fast and cheap — good for bulk extraction).
        api_key: Optional override. If omitted, uses ANTHROPIC_API_KEY env var.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Anthropic API key not found. Set the ANTHROPIC_API_KEY "
                "environment variable or pass api_key= explicitly."
            )
        try:
            import anthropic  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required for AnthropicBackend.\n"
                "Install it with:  pip install anthropic"
            ) from exc
        self._anthropic = anthropic
        self._client = None

    def complete(self, system: str, user: str) -> str:
        if self._client is None:
            # max_retries=6: SDK retries 429/5xx with exponential backoff
            # (1s, 2s, 4s, 8s, 16s, 32s) before raising
            self._client = self._anthropic.Anthropic(
                api_key=self._api_key,
                max_retries=6,
                timeout=_llm_timeout(),
            )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if not message.content:
            return ""
        block = message.content[0]
        return getattr(block, "text", "") or ""
