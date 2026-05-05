from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, OWL, RDF, RDFS, SKOS, XSD

from ontobridge.models.enums import LifecycleStatus
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
