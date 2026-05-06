from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, OWL, RDF, RDFS, SKOS, XSD

from ontobridge.models.enums import LifecycleStatus
from ontobridge.models.published import PublishedTerm
from ontobridge.publisher.base import TermPublisher

_ONTOLOGY_URI = URIRef("http://ontobridge.dev/ontology/glossary/")
_BANK = "http://ontobridge.dev/ontology/bank/"
_REL = "http://ontobridge.dev/ontology/bank/relations/"


def _base_graph() -> Graph:
    g = Graph()
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("skos", SKOS)
    g.bind("dc", DC)
    g.bind("xsd", XSD)
    g.bind("bank", URIRef(_BANK))
    g.bind("rel", URIRef(_REL))
    return g


def export_turtle(
    publisher: TermPublisher,
    *,
    statuses: set[LifecycleStatus] | None = None,
    title: str = "OntoBridge Term Glossary",
    output_path: Path | str | None = None,
) -> str:
    """Merge per-term Turtle snippets into a single .ttl file.

    Args:
        publisher:   Source of terms.
        statuses:    Lifecycle statuses to include.  Defaults to
                     ``{PUBLISHED}`` — only glossary-ready terms.
                     Pass ``None`` to use the default, or an explicit set to
                     include e.g. REVIEW terms during a demo.
        title:       ``owl:Ontology`` label written into the file header.
        output_path: If given, the merged Turtle is also written to this path.

    Returns:
        The merged Turtle string.
    """
    if statuses is None:
        statuses = {LifecycleStatus.PUBLISHED}

    all_terms = publisher.search_terms("")
    selected = [t for t in all_terms if t.lifecycle_status in statuses]

    g = _base_graph()

    # Ontology header
    g.add((_ONTOLOGY_URI, RDF.type, OWL.Ontology))
    g.add((_ONTOLOGY_URI, RDFS.label, Literal(title, lang="en")))
    g.add((
        _ONTOLOGY_URI,
        DC.date,
        Literal(datetime.now(timezone.utc).date().isoformat(), datatype=XSD.date),
    ))
    g.add((
        _ONTOLOGY_URI,
        DC.description,
        Literal(
            f"Auto-exported by OntoBridge. "
            f"Contains {len(selected)} term(s) with status: "
            f"{', '.join(s.value for s in statuses)}.",
            lang="en",
        ),
    ))

    # Merge per-term graphs
    skipped = 0
    for term in selected:
        if not term.turtle:
            skipped += 1
            continue
        try:
            term_graph = Graph()
            term_graph.parse(data=term.turtle, format="turtle")
            for triple in term_graph:
                g.add(triple)
        except Exception:
            skipped += 1

    ttl = g.serialize(format="turtle")

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ttl, encoding="utf-8")

    return ttl


_CSV_COLUMNS = [
    "label",
    "definition",
    "alt_labels",
    "scheme",
    "status",
    "approved_by",
    "term_uri",
]


def _term_to_csv_row(term: PublishedTerm) -> dict:
    enriched = term.enriched_term
    pref = enriched.preferred_label or ""
    alts = [c.text for c in enriched.candidate_labels if c.text != pref]
    placement = enriched.taxonomy_placement
    scheme = ""
    if placement and placement.scheme_uri:
        scheme = placement.scheme_uri.rstrip("/").split("/")[-1]
    return {
        "label": pref,
        "definition": enriched.definition or "",
        "alt_labels": "; ".join(alts),
        "scheme": scheme,
        "status": term.lifecycle_status.value,
        "approved_by": term.approved_by or "",
        "term_uri": term.term_uri,
    }


def export_glossary_csv(
    publisher: TermPublisher,
    *,
    statuses: set[LifecycleStatus] | None = None,
) -> str:
    """Export terms as a UTF-8 CSV string.

    Args:
        publisher: Source of terms.
        statuses:  Lifecycle statuses to include.  Defaults to ``{PUBLISHED}``.

    Returns:
        CSV text (header row + one row per term, sorted by label).
    """
    if statuses is None:
        statuses = {LifecycleStatus.PUBLISHED}

    terms = [
        t for t in publisher.search_terms("")
        if t.lifecycle_status in statuses
    ]
    terms.sort(key=lambda t: (t.enriched_term.preferred_label or "").lower())

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for term in terms:
        writer.writerow(_term_to_csv_row(term))

    return buf.getvalue()


def export_all_statuses(
    publisher: TermPublisher,
    *,
    title: str = "OntoBridge Full Term Export",
    output_path: Path | str | None = None,
) -> str:
    """Export every term regardless of lifecycle status.

    Useful for audits, debugging, or handing off to the professor.
    """
    return export_turtle(
        publisher,
        statuses=set(LifecycleStatus),
        title=title,
        output_path=output_path,
    )
