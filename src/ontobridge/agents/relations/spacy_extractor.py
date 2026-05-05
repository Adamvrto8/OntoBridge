from __future__ import annotations

from typing import TYPE_CHECKING

from ontobridge.agents.relations.extractor import SVOExtractor, SVOTriple

if TYPE_CHECKING:
    import spacy
    from spacy.tokens import Doc, Span, Token


# Dependency relations that indicate a nominal subject
_SUBJ_DEPS = {"nsubj", "nsubjpass", "csubj"}

# Dependency relations that indicate a direct or prepositional object
_OBJ_DEPS = {"dobj", "attr", "acomp", "oprd"}

# Dependency relations for verb tokens worth extracting from
_VERB_DEPS = {"ROOT", "relcl", "advcl", "conj"}


class SpaCyExtractor(SVOExtractor):
    """SVO extractor backed by spaCy's dependency parser.

    Uses the full dependency parse tree to find genuine subject-verb-object
    relations rather than regex heuristics.  Noun phrases are expanded via
    spaCy's noun-chunk detection so "the retail customer" rather than just
    "customer" is returned as the subject text.

    Confidence is set to 0.90 for root-verb triples (parser is confident)
    and 0.70 for triples found in relative or adverbial clauses.

    Args:
        model:   spaCy model name.  Defaults to ``en_core_web_sm``.
                 The model is loaded lazily on the first ``extract()`` call.
    """

    def __init__(self, model: str = "en_core_web_sm") -> None:
        self.model_name = model
        self._nlp = None  # lazy-loaded

    # ------------------------------------------------------------------
    # SVOExtractor interface
    # ------------------------------------------------------------------

    def extract(
        self, text: str, *, default_subject: str | None = None
    ) -> list[SVOTriple]:
        if not text or not text.strip():
            return []
        nlp = self._get_nlp()
        doc = nlp(text)
        triples: list[SVOTriple] = []
        for sent in doc.sents:
            triples.extend(self._from_sentence(sent, default_subject))
        return triples

    # ------------------------------------------------------------------
    # Sentence-level extraction
    # ------------------------------------------------------------------

    def _from_sentence(
        self, sent: Span, default_subject: str | None
    ) -> list[SVOTriple]:
        # Build a token → noun-chunk-text map for this sentence so we can
        # replace bare heads with full NP spans.
        chunk_map: dict[int, str] = {}
        for chunk in sent.as_doc()[sent.start : sent.end].noun_chunks:
            # chunk indices are relative to doc; offset by sent.start
            chunk_map[sent.start + chunk.root.i] = chunk.text

        triples: list[SVOTriple] = []
        for token in sent:
            if token.pos_ not in ("VERB", "AUX"):
                continue
            if token.dep_ not in _VERB_DEPS:
                continue

            subj_text = self._subject(token, chunk_map)
            if subj_text is None:
                subj_text = default_subject
            if not subj_text:
                continue

            obj_text = self._object(token, chunk_map)
            if not obj_text:
                continue

            confidence = 0.90 if token.dep_ == "ROOT" else 0.70
            triples.append(
                SVOTriple(
                    subject=subj_text.strip(),
                    verb=token.lemma_.casefold(),
                    object=obj_text.strip(),
                    confidence=confidence,
                    source_text=sent.text.strip(),
                )
            )
        return triples

    # ------------------------------------------------------------------
    # Subject / object resolution
    # ------------------------------------------------------------------

    def _subject(self, verb: Token, chunk_map: dict[int, str]) -> str | None:
        for child in verb.children:
            if child.dep_ in _SUBJ_DEPS:
                return chunk_map.get(child.i, child.text)
        # Passive: "account is held by customer" — find the pobj of the agent
        for child in verb.children:
            if child.dep_ == "agent":
                for gc in child.children:
                    if gc.dep_ == "pobj":
                        return chunk_map.get(gc.i, gc.text)
        return None

    def _object(self, verb: Token, chunk_map: dict[int, str]) -> str | None:
        # Direct or attributive object
        for child in verb.children:
            if child.dep_ in _OBJ_DEPS:
                return chunk_map.get(child.i, child.text)
        # Prepositional object: "applies to retail customer"
        for child in verb.children:
            if child.dep_ == "prep":
                for gc in child.children:
                    if gc.dep_ == "pobj":
                        np = chunk_map.get(gc.i, gc.text)
                        return f"{child.text} {np}"
        return None

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _get_nlp(self) -> spacy.Language:
        if self._nlp is None:
            try:
                import spacy as _spacy
            except ImportError as exc:
                raise ImportError(
                    "spaCy is required for SpaCyExtractor.\n"
                    "Install it with:  pip install spacy\n"
                    "Then download the model:  python -m spacy download en_core_web_sm"
                ) from exc
            try:
                self._nlp = _spacy.load(self.model_name)
            except OSError as exc:
                raise OSError(
                    f"spaCy model {self.model_name!r} not found.\n"
                    f"Download it with:  python -m spacy download {self.model_name}"
                ) from exc
        return self._nlp

    def __repr__(self) -> str:
        loaded = self._nlp is not None
        return f"SpaCyExtractor(model={self.model_name!r}, loaded={loaded})"
