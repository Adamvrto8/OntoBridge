from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SVOTriple:
    subject: str
    verb: str
    object: str
    confidence: float = 1.0
    source_text: str | None = None


class SVOExtractor(ABC):
    @abstractmethod
    def extract(
        self, text: str, *, default_subject: str | None = None
    ) -> list[SVOTriple]:
        ...


_SENTENCE_SPLIT = re.compile(r"[.!?;]+\s*")
_CLAUSE_CONNECTOR = re.compile(
    r"\b(?:who|that|which|while|when|where)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]*")

_LEADING_OBJ_FILLERS = frozenset({"and", "or", "then", "also", "to"})
_TRAILING_OBJ_FILLERS = frozenset({"and", "or", "the", "a", "an"})

# Single-word determiners: if one of these is the only text before a vocab
# word, the vocab word is being used as a noun ("A record of…"), not a verb.
_BARE_DETERMINERS = frozenset({"a", "an", "the", "this", "that", "these", "those"})

# Max tokens allowed in an extracted object phrase. Longer spans are almost
# always a sign the "verb" was actually a noun and the parser went off the rails.
_MAX_OBJ_TOKENS = 7

DEFAULT_VERB_VOCAB: frozenset[str] = frozenset({
    # original lexicon verbs (resolve to ontology property URIs)
    "holds", "hold",
    "submits", "submit",
    "uses", "use",
    "evaluates", "evaluate",
    "requires", "require",
    "produces", "produce",
    "governs", "govern",
    "triggers", "trigger",
    "creates", "create",
    "validates", "validate",
    "manages", "manage",
    "approves", "approve",
    "rejects", "reject",
    "verifies", "verify",
    "assesses", "assess",
    "calculates", "calculate",
    "determines", "determine",
    "generates", "generate",
    "owns", "own",
    # banking/document verbs — kept only where the word is unambiguously
    # a verb and not commonly a standalone noun in banking prose
    "allows", "allow",
    "enables", "enable",
    "provides", "provide",
    "contains", "contain",
    "stores", "store",
    "retrieves", "retrieve",
    "sends", "send",
    "receives", "receive",
    "connects", "connect",
    "includes", "include",
    "represents", "represent",
    "defines", "define",
    "identifies", "identify",
    "classifies", "classify",
    "executes", "execute",
    "initiates", "initiate",
    "authorizes", "authorize",
    "authenticates", "authenticate",
    "applies", "apply",
    "enforces", "enforce",
    "restricts", "restrict",
    "protects", "protect",
    "notifies", "notify",
    "aggregates", "aggregate",
    "consolidates", "consolidate",
    "assigns", "assign",
    "locates", "locate",
    "captures", "capture",
    "extracts", "extract",
    "filters", "filter",
    "views", "view",
    "downloads", "download",
    "uploads", "upload",
    "shows", "show",
    "supports", "support",
    "handles", "handle",
    "tracks", "track",
    "links", "link",
    "accesses", "access",
    # removed: record/records, process/processes, review/reviews,
    # issue/issues, display/displays, report/reports, monitor/monitors,
    # control/controls, limit/limits, alert/alerts, format/formats,
    # schedule/schedules, transfer/transfers, grant/grants, associate/associates
    # — all predominantly used as nouns in banking definitions
})


def _strip_trailing_punct(s: str) -> str:
    return s.strip().rstrip(",;:.")


class RegexHeuristicExtractor(SVOExtractor):
    """Surface-level SVO extractor: strip relative-clause connectors, find
    verbs from a curated vocabulary, slice subject/object NPs around them.

    Deliberately separate from the lexicon — a real spaCy- or LLM-based
    extractor can replace this without touching the RelationsAgent."""

    def __init__(self, vocab: Iterable[str] | None = None):
        self.vocab: frozenset[str] = (
            frozenset(v.casefold() for v in vocab)
            if vocab is not None
            else DEFAULT_VERB_VOCAB
        )

    def extract(
        self, text: str, *, default_subject: str | None = None
    ) -> list[SVOTriple]:
        if not text or not text.strip():
            return []
        triples: list[SVOTriple] = []
        for sentence in self._sentences(text):
            triples.extend(self._extract_from_sentence(sentence, default_subject))
        return triples

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]

    def _extract_from_sentence(
        self, sentence: str, default_subject: str | None
    ) -> list[SVOTriple]:
        clean = _CLAUSE_CONNECTOR.sub(" ", sentence)
        tokens = _TOKEN_RE.findall(clean)
        if not tokens:
            return []

        verb_indices = [
            i for i, t in enumerate(tokens) if t.casefold() in self.vocab
        ]
        if not verb_indices:
            return []

        first = verb_indices[0]
        leading = " ".join(tokens[:first]).strip()

        # If the only text before the first vocab word is a bare determiner
        # ("A record of…", "The display that…"), the word is a noun, not a verb.
        # Use the term label as subject and skip that false verb entirely.
        if leading.casefold() in _BARE_DETERMINERS:
            sentence_subject = default_subject or ""
            verb_indices = verb_indices[1:]
        else:
            sentence_subject = leading or (default_subject or "")

        if not sentence_subject or not verb_indices:
            return []

        triples: list[SVOTriple] = []
        for i, vi in enumerate(verb_indices):
            end = (
                verb_indices[i + 1]
                if i + 1 < len(verb_indices)
                else len(tokens)
            )
            obj_tokens = tokens[vi + 1 : end]
            while obj_tokens and obj_tokens[0].casefold() in _LEADING_OBJ_FILLERS:
                obj_tokens = obj_tokens[1:]
            while obj_tokens and obj_tokens[-1].casefold() in _TRAILING_OBJ_FILLERS:
                obj_tokens = obj_tokens[:-1]
            if not obj_tokens or len(obj_tokens) > _MAX_OBJ_TOKENS:
                continue
            triples.append(
                SVOTriple(
                    subject=_strip_trailing_punct(sentence_subject),
                    verb=tokens[vi].casefold(),
                    object=_strip_trailing_punct(" ".join(obj_tokens)),
                    source_text=sentence.strip() or None,
                )
            )
        return triples
