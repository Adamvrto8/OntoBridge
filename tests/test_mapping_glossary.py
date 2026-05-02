from __future__ import annotations

from ontobridge.agents.mapping import (
    GlossaryEntry,
    ListGlossarySource,
    from_entries,
    from_ontology,
    from_publisher,
    from_published_terms,
)
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    PublishedTerm,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.publisher import InMemoryPublisher


def _published(uri: str, pref: str, alts: list[str] | None = None, defn: str | None = None) -> PublishedTerm:
    enriched = EnrichedTerm.from_harvest(
        HarvestRecord(
            text=defn or pref,
            source_type=SourceType.USER_INPUT,
            source_ref=SourceRef(source_system="ui"),
            tier=Tier.UNSTRUCTURED,
        )
    )
    enriched.definition = defn
    labels = [CandidateLabel(text=pref, confidence=0.95)]
    for i, a in enumerate(alts or []):
        labels.append(CandidateLabel(text=a, confidence=0.5 - i * 0.01))
    enriched.candidate_labels = labels
    return PublishedTerm(
        enriched_term=enriched,
        term_uri=uri,
        lifecycle_status=LifecycleStatus.DRAFT,
    )


def test_from_entries_round_trip():
    e = [GlossaryEntry(uri="ex:A", pref_label="A")]
    g = from_entries(e)
    assert isinstance(g, ListGlossarySource)
    assert list(g.entries()) == e


def test_from_ontology_loads_v0_1_concepts(base_ontology):
    g = from_ontology(base_ontology)
    pref_labels = {e.pref_label for e in g.entries()}
    assert "Retail customer" in pref_labels
    assert "Mobile app" in pref_labels
    assert "PI customer" in {alt for e in g.entries() for alt in e.alt_labels}


def test_from_published_terms_picks_highest_confidence_as_pref():
    term = _published("bank:Foo", pref="Retail customer", alts=["RC"])
    g = from_published_terms([term])
    entry = next(g.entries())
    assert entry.pref_label == "Retail customer"
    assert "RC" in entry.alt_labels


def test_from_published_terms_skips_term_with_no_labels():
    enriched = EnrichedTerm.from_harvest(
        HarvestRecord(
            text="x",
            source_type=SourceType.USER_INPUT,
            source_ref=SourceRef(source_system="ui"),
            tier=Tier.UNSTRUCTURED,
        )
    )
    pt = PublishedTerm(enriched_term=enriched, term_uri="bank:Empty")
    g = from_published_terms([pt])
    assert list(g.entries()) == []


def test_from_publisher_uses_search_terms():
    pub = InMemoryPublisher()
    pub.create_term(_published("bank:Foo", "Retail customer"))
    pub.create_term(_published("bank:Bar", "Corporate customer"))
    g = from_publisher(pub)
    uris = sorted(e.uri for e in g.entries())
    assert uris == ["bank:Bar", "bank:Foo"]
