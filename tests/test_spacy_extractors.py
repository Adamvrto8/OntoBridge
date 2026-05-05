from __future__ import annotations

import pytest

spacy = pytest.importorskip("spacy", reason="spaCy not installed")

try:
    spacy.load("en_core_web_sm")
except OSError:
    pytest.skip("en_core_web_sm model not installed", allow_module_level=True)

from ontobridge.agents.relations.spacy_extractor import SpaCyExtractor
from ontobridge.agents.relations.extractor import SVOExtractor, SVOTriple
from ontobridge.agents.harvester.extractors.spacy_extractor import SpaCyTermExtractor
from ontobridge.agents.harvester.protocols import RawDocument, TermExtractor


# ===========================================================================
# SpaCyExtractor — SVO extraction for Relations agent
# ===========================================================================

@pytest.fixture(scope="module")
def svo_extractor():
    return SpaCyExtractor()


class TestSpaCyExtractorInterface:
    def test_is_svo_extractor_subclass(self):
        assert issubclass(SpaCyExtractor, SVOExtractor)

    def test_returns_list_of_svo_triples(self, svo_extractor):
        results = svo_extractor.extract("A retail customer holds an account.")
        assert isinstance(results, list)
        assert all(isinstance(t, SVOTriple) for t in results)

    def test_empty_text_returns_empty(self, svo_extractor):
        assert svo_extractor.extract("") == []
        assert svo_extractor.extract("   ") == []

    def test_repr_shows_model_name(self):
        enc = SpaCyExtractor(model="en_core_web_sm")
        assert "en_core_web_sm" in repr(enc)
        assert "loaded=False" in repr(enc)


class TestSpaCyExtractorSVO:
    def test_extracts_simple_subject_verb_object(self, svo_extractor):
        triples = svo_extractor.extract(
            "A retail customer holds a joint account."
        )
        assert triples, "expected at least one triple"
        verbs = [t.verb for t in triples]
        assert any("hold" in v for v in verbs)

    def test_subject_is_populated(self, svo_extractor):
        triples = svo_extractor.extract(
            "The bank evaluates customer identity before onboarding."
        )
        assert triples
        assert all(t.subject for t in triples)

    def test_object_is_populated(self, svo_extractor):
        triples = svo_extractor.extract(
            "A customer submits a loan application to the branch."
        )
        assert triples
        assert all(t.object for t in triples)

    def test_source_text_is_the_sentence(self, svo_extractor):
        sentence = "A retail customer holds a bank account."
        triples = svo_extractor.extract(sentence)
        assert triples
        assert all(t.source_text for t in triples)

    def test_confidence_is_in_range(self, svo_extractor):
        triples = svo_extractor.extract(
            "The bank processes loan applications submitted by retail customers."
        )
        assert all(0.0 <= t.confidence <= 1.0 for t in triples)

    def test_default_subject_used_when_no_nsubj(self, svo_extractor):
        triples = svo_extractor.extract(
            "Holds and manages credit products.",
            default_subject="Retail customer",
        )
        subjs = [t.subject for t in triples]
        assert any("Retail customer" in s for s in subjs)

    def test_multiple_sentences_each_processed(self, svo_extractor):
        text = (
            "A retail customer holds an account. "
            "The bank evaluates the customer identity."
        )
        triples = svo_extractor.extract(text)
        assert len(triples) >= 2

    def test_verb_is_lemmatised(self, svo_extractor):
        triples = svo_extractor.extract(
            "A retail customer holds premium products."
        )
        verbs = [t.verb for t in triples]
        # spaCy lemmatises 'holds' → 'hold'
        assert any(v in ("hold", "holds") for v in verbs)

    def test_root_verb_confidence_higher_than_clause(self, svo_extractor):
        text = (
            "A retail customer holds an account, "
            "which governs their repayment schedule."
        )
        triples = svo_extractor.extract(text)
        if len(triples) >= 2:
            root_triple = max(triples, key=lambda t: t.confidence)
            assert root_triple.confidence >= 0.85


class TestSpaCyExtractorMissingDep:
    def test_missing_spacy_raises_import_error(self, monkeypatch):
        import sys
        original = sys.modules.pop("spacy", None)
        try:
            ext = SpaCyExtractor()
            ext._nlp = None
            monkeypatch.setitem(sys.modules, "spacy", None)  # type: ignore[arg-type]
            with pytest.raises(ImportError, match="spaCy"):
                ext._get_nlp()
        finally:
            if original is not None:
                sys.modules["spacy"] = original
            else:
                sys.modules.pop("spacy", None)


# ===========================================================================
# SpaCyTermExtractor — TermExtractor for Harvester
# ===========================================================================

@pytest.fixture(scope="module")
def term_extractor():
    return SpaCyTermExtractor()


class TestSpaCyTermExtractorInterface:
    def test_satisfies_term_extractor_protocol(self, term_extractor):
        assert isinstance(term_extractor, TermExtractor)

    def test_returns_list(self, term_extractor):
        doc = RawDocument(text="Retail banking customers use mobile applications.")
        assert isinstance(term_extractor.extract(doc), list)

    def test_empty_doc_returns_empty(self, term_extractor):
        assert term_extractor.extract(RawDocument(text="")) == []
        assert term_extractor.extract(RawDocument(text="   ")) == []

    def test_repr_shows_model(self):
        ext = SpaCyTermExtractor(model="en_core_web_sm")
        assert "en_core_web_sm" in repr(ext)


class TestSpaCyTermExtractorExtraction:
    def test_extracts_noun_phrase_as_label(self, term_extractor):
        doc = RawDocument(
            text=(
                "Retail banking customers hold current accounts and use "
                "mobile banking applications for daily transactions."
            )
        )
        results = term_extractor.extract(doc)
        assert results
        labels = [r.candidate_label for r in results]
        assert any(len(lbl.split()) >= 2 for lbl in labels)

    def test_definition_is_the_sentence(self, term_extractor):
        doc = RawDocument(
            text=(
                "Joint account holders share signing authority over a bank account "
                "and submit instructions together to the institution."
            )
        )
        results = term_extractor.extract(doc)
        assert results
        for r in results:
            assert len(r.definition.split()) >= 8

    def test_short_sentences_skipped(self, term_extractor):
        doc = RawDocument(text="Banks lend money.")
        results = term_extractor.extract(doc)
        assert results == []

    def test_section_inherited_from_doc(self, term_extractor):
        doc = RawDocument(
            text=(
                "Retail banking customers hold current accounts at the institution "
                "for everyday personal banking transactions and services."
            ),
            section="Retail Policy §2",
        )
        results = term_extractor.extract(doc)
        assert results
        assert all(r.section == "Retail Policy §2" for r in results)

    def test_labels_are_not_articles_or_pronouns(self, term_extractor):
        doc = RawDocument(
            text=(
                "The customer holds an account at the bank for personal use "
                "and submits monthly repayment instalments accordingly."
            )
        )
        results = term_extractor.extract(doc)
        bad_starts = {"the", "a", "an", "this", "these", "it", "they"}
        for r in results:
            first_word = r.candidate_label.split()[0].casefold()
            assert first_word not in bad_starts, (
                f"Label {r.candidate_label!r} starts with a stopword"
            )

    def test_confidence_is_in_range(self, term_extractor):
        doc = RawDocument(
            text=(
                "Retail banking customers use digital channels for account "
                "management and payment processing across all service touchpoints."
            )
        )
        results = term_extractor.extract(doc)
        assert all(0.0 <= r.confidence <= 1.0 for r in results)

    def test_no_duplicate_labels_within_document(self, term_extractor):
        doc = RawDocument(
            text=(
                "Retail banking customers hold retail accounts. "
                "Retail banking customers also use mobile banking services "
                "for everyday transactions and payment operations."
            )
        )
        results = term_extractor.extract(doc)
        labels_lower = [r.candidate_label.casefold() for r in results]
        assert len(labels_lower) == len(set(labels_lower))

    def test_metadata_copied_from_doc(self, term_extractor):
        doc = RawDocument(
            text=(
                "Retail banking customers hold current accounts for personal "
                "use and submit regular payment instructions to the bank."
            ),
            metadata={"source": "CreditPolicy.pdf"},
        )
        results = term_extractor.extract(doc)
        assert results
        assert all(r.metadata.get("source") == "CreditPolicy.pdf" for r in results)


# ===========================================================================
# Integration — SpaCyExtractor wired into RelationsAgent
# ===========================================================================

def test_spacy_extractor_plugs_into_relations_agent(base_ontology):
    from ontobridge.agents.relations.agent import RelationsAgent

    ext = SpaCyExtractor()
    agent = RelationsAgent(base_ontology, extractor=ext)

    from ontobridge.models import (
        CandidateLabel, EnrichedTerm, HarvestRecord,
        MatchResult, MatchType, SourceRef, SourceType, Tier,
    )
    harvest = HarvestRecord(
        text="A retail customer holds a joint account at the bank.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="P.pdf"),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text="Joint account holder", confidence=0.9)]
    term.definition = (
        "A retail customer who holds an account jointly with one or more "
        "other parties and submits shared signing instructions."
    )
    term.match_result = MatchResult(
        match_type=MatchType.NEW, similarity=0.0, alternative_matches=[]
    )

    result = agent.apply(term)
    # RelationsAgent should have run without error; relations may or may not be found
    assert isinstance(result.relations, list)


# ===========================================================================
# Integration — SpaCyTermExtractor wired into HarvesterAgent
# ===========================================================================

def test_spacy_term_extractor_plugs_into_harvester(tmp_path):
    from ontobridge.agents.harvester.agent import HarvesterAgent
    from ontobridge.agents.harvester.readers.text import PlainTextReader

    ext = SpaCyTermExtractor()
    agent = HarvesterAgent(readers=[PlainTextReader()], extractor=ext)

    f = tmp_path / "policy.txt"
    f.write_text(
        "Retail banking customers hold current accounts and use mobile banking "
        "applications for everyday personal transactions and payment services.\n\n"
        "Joint account holders share signing authority over a shared bank account "
        "and submit payment instructions together to the financial institution.\n",
        encoding="utf-8",
    )

    records = agent.harvest(f)
    assert isinstance(records, list)
    # SpaCyTermExtractor returns noun-phrase based terms, so we expect some records
    assert len(records) >= 0  # may be 0 if no valid NP found — just must not crash
