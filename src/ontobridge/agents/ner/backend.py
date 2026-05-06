from __future__ import annotations

from typing import Protocol, runtime_checkable


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
            )

        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = self._llm.invoke(messages)
        return str(response.content)
