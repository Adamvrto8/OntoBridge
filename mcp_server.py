"""OntoBridge MCP Server

Exposes OntoBridge term governance as MCP tools usable from Claude desktop,
Claude Code, or any MCP-compatible client.

Install dependencies:
    pip install fastmcp httpx

Configuration (env vars):
    ONTOBRIDGE_URL   Base URL of the OntoBridge API (default: http://localhost:8001)
                     Change to the GCP URL when deployed to cloud.

Claude desktop config (~/.claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "ontobridge": {
                "command": "python",
                "args": ["C:/SKOLA/DATA PROJEKT/ontobridge/mcp_server.py"],
                "env": { "ONTOBRIDGE_URL": "http://localhost:8001" }
            }
        }
    }

Claude Code config (.claude/settings.json in this repo):
    {
        "mcpServers": {
            "ontobridge": {
                "command": "python",
                "args": ["mcp_server.py"],
                "env": { "ONTOBRIDGE_URL": "http://localhost:8001" }
            }
        }
    }

Run standalone (for testing):
    python mcp_server.py
"""

from __future__ import annotations

import io
import json
import os
from typing import Optional

import httpx
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration — GCP-ready: just change ONTOBRIDGE_URL to the cloud URL
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("ONTOBRIDGE_URL", "http://localhost:8001").rstrip("/")

mcp = FastMCP(
    name="OntoBridge",
    instructions=(
        "OntoBridge is a semantic term governance system for retail banking. "
        "Use it to search the published glossary, review terms awaiting approval, "
        "submit documents for term extraction, and manage the term lifecycle. "
        "Always prefer searching the glossary before extracting new terms — "
        "the term may already exist."
    ),
)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(path: str, **params) -> dict | list:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get(f"/api{path}", params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


def _patch(path: str, body: dict) -> dict:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.patch(f"/api{path}", json=body)
        r.raise_for_status()
        return r.json()


def _post_form(path: str, data: dict, files: dict | None = None) -> dict:
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        r = client.post(f"/api{path}", data=data, files=files)
        r.raise_for_status()
        return r.json()


def _fmt_term(t: dict) -> str:
    lines = [
        f"**{t.get('preferred_label', '—')}**  ({t.get('lifecycle_status', '—')})",
        f"URI: {t.get('term_uri', '—')}",
        f"Scheme: {t.get('scheme_label') or '—'}",
        f"Definition: {t.get('definition') or 'No definition.'}",
    ]
    if t.get("severity") and t["severity"] != "low":
        lines.append(f"Severity: {t['severity']}")
    if t.get("issue_type"):
        lines.append(f"Issue: {t['issue_type']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_stats() -> str:
    """Return an overview of the OntoBridge glossary: total terms, status breakdown,
    definition coverage by scheme, and recent audit activity."""
    s = _get("/stats")
    by_status = s.get("by_status", {})
    by_scheme = s.get("by_scheme", {})
    lines = [
        f"Total terms: {s.get('total', 0)}",
        f"With definition: {s.get('with_definition', 0)}",
        f"Audit events: {s.get('recent_activity', 0)}",
        "",
        "Status breakdown:",
        *[f"  {k}: {v}" for k, v in by_status.items()],
        "",
        "Definition coverage by scheme (% terms with definition):",
        *[f"  {k}: {v}%" for k, v in by_scheme.items()],
    ]
    return "\n".join(lines)


@mcp.tool()
def search_glossary(query: str, status: Optional[str] = None) -> str:
    """Search OntoBridge for terms matching a label or definition text.

    Args:
        query:  Search string — matched against term labels and definitions.
        status: Optional filter — one of: candidate, draft, review, published, deprecated.
                Omit to search all statuses.

    Returns a list of matching terms with their definitions and lifecycle status.
    """
    params = {"search": query}
    if status:
        params["status"] = status
    terms = _get("/terms", **params)
    if not terms:
        return f"No terms found matching '{query}'."
    lines = [f"Found {len(terms)} term(s) matching '{query}':\n"]
    for t in terms[:20]:  # cap at 20 to keep context manageable
        lines.append(_fmt_term(t))
        lines.append("")
    if len(terms) > 20:
        lines.append(f"... and {len(terms) - 20} more. Refine your query to narrow results.")
    return "\n".join(lines)


@mcp.tool()
def get_term(uri: str) -> str:
    """Get the full detail of a specific term by its URI.

    Args:
        uri: The term URI (e.g. http://ontobridge.dev/ontology/bank/Loan).
             Use search_glossary first to find the URI.

    Returns definition, alt labels, taxonomy placement with ancestor path,
    semantic relations, governance issues, and metadata.
    """
    t = _get(f"/terms/{uri}")
    lines = [
        f"# {t.get('preferred_label', '—')}",
        f"URI: {t.get('term_uri')}",
        f"Status: {t.get('lifecycle_status')}  |  Version: v{t.get('version', 1)}",
        f"Approved by: {t.get('approved_by') or '—'}",
        "",
        "## Definition",
        t.get("definition") or "No definition.",
        "",
    ]

    if t.get("alt_labels"):
        lines += ["## Alt labels", ", ".join(t["alt_labels"]), ""]

    if t.get("ancestor_path") or t.get("broader_label"):
        path = " › ".join(t.get("ancestor_path", []))
        if t.get("scheme_label"):
            path = f"{t['scheme_label']} › {path}" if path else t["scheme_label"]
        lines += ["## Taxonomy", path or t.get("broader_label") or "—", ""]

    if t.get("relations"):
        lines.append("## Semantic relations")
        for r in t["relations"]:
            obj_uri = f"  ({r['object_uri'].split('/')[-1]})" if r.get("object_uri") else ""
            lines.append(f"  {r['predicate']} → {r['object_label']}{obj_uri}")
        lines.append("")

    if t.get("business_rules"):
        lines.append("## Business rules")
        for rule in t["business_rules"]:
            lines.append(f"  • {rule}")
        lines.append("")

    if t.get("issue_type"):
        lines += [
            "## Governance issue",
            f"  Type: {t['issue_type']}",
            f"  Rule: {t.get('issue_rule', '—')}",
            f"  Severity: {t.get('severity', '—')}",
            "",
        ]

    lines += [
        "## Metadata",
        f"  Source: {t.get('source_system') or '—'}",
        f"  Document: {t.get('document_id') or '—'}",
        f"  Confidence: {int((t.get('confidence') or 0) * 100)}%",
    ]
    return "\n".join(lines)


@mcp.tool()
def list_inbox(severity: Optional[str] = None) -> str:
    """List terms in the governance inbox awaiting steward review.

    Args:
        severity: Optional filter — one of: crit, high, med, low.
                  Omit to list all severities.

    Returns terms sorted by severity with their governance issues.
    """
    terms = _get("/terms", status="review")
    if severity:
        terms = [t for t in terms if t.get("severity") == severity]
    if not terms:
        return "Governance inbox is empty." if not severity else f"No terms with severity '{severity}'."
    lines = [f"{len(terms)} term(s) awaiting review:\n"]
    for t in terms:
        lines.append(
            f"[{(t.get('severity') or 'low').upper()}] **{t.get('preferred_label')}**\n"
            f"  Issue: {t.get('issue_type') or 'Pending review'}\n"
            f"  URI: {t.get('term_uri')}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def approve_term(uri: str, actor: str) -> str:
    """Approve a term — transition it to PUBLISHED status.

    Args:
        uri:   Term URI. Use search_glossary or list_inbox to find it.
        actor: Your name as the approving steward. Required for PUBLISHED status.

    Only terms in REVIEW status can be published directly.
    Terms in CANDIDATE or DRAFT must be moved to REVIEW first.
    """
    result = _patch(f"/terms/{uri}/status", {"new_status": "published", "actor": actor})
    label = result.get("preferred_label", uri)
    status = result.get("lifecycle_status", "—")
    return f"'{label}' transitioned to {status}. Approved by: {actor}."


@mcp.tool()
def transition_term(uri: str, new_status: str, actor: Optional[str] = None) -> str:
    """Move a term to a different lifecycle status.

    Args:
        uri:        Term URI.
        new_status: Target status — one of: draft, review, published, deprecated, candidate.
        actor:      Your name (required when publishing).

    Valid transitions:
        candidate → draft, review
        draft     → review, candidate
        review    → published (requires actor), draft, candidate
        published → deprecated, review
    """
    body: dict = {"new_status": new_status}
    if actor:
        body["actor"] = actor
    result = _patch(f"/terms/{uri}/status", body)
    label = result.get("preferred_label", uri)
    return f"'{label}' is now {result.get('lifecycle_status')}."


@mcp.tool()
def submit_text(
    text: str,
    document_name: Optional[str] = "mcp_submission.txt",
    use_llm: bool = False,
) -> str:
    """Submit a block of text to the OntoBridge pipeline for term extraction.

    The pipeline will extract banking terms, enrich them with FIBO and taxonomy
    placement, evaluate governance rules, and add them to the glossary inbox.

    Args:
        text:          The text to extract terms from. Can be a policy excerpt,
                       email body, procedure description, or any banking document.
        document_name: A name for this submission (used as the document reference
                       in term metadata). Default: mcp_submission.txt
        use_llm:       If True, uses Claude (AnthropicBackend) for higher-quality
                       extraction. Requires ANTHROPIC_API_KEY on the server.
                       If False, uses fast pattern-based extraction.

    Returns a summary of extracted terms and their governance outcomes.
    """
    file_bytes = text.encode("utf-8")
    files = {"file": (document_name, io.BytesIO(file_bytes), "text/plain")}
    data = {
        "use_llm_extractor": str(use_llm).lower(),
        "improve_definitions": "false",
        "llm_backend": "anthropic" if use_llm else "ollama",
        "llm_model": "claude-haiku-4-5-20251001",
    }
    result = _post_form("/pipeline/run", data=data, files=files)

    terms = result.get("terms", [])
    if not terms:
        return "Pipeline ran but extracted no terms. Try a longer or more structured text."

    lines = [f"Extracted {len(terms)} term(s):\n"]
    for t in terms:
        action = t.get("recommended_action", "—")
        lines.append(
            f"  • **{t.get('preferred_label')}**  [{action.upper()}]\n"
            f"    {(t.get('definition') or '')[:120]}{'…' if len(t.get('definition') or '') > 120 else ''}"
        )
    lines.append(
        f"\nTerms are now in the governance inbox. "
        f"Use list_inbox() to review them and approve_term() to publish."
    )
    return "\n".join(lines)


@mcp.tool()
def edit_definition(uri: str, definition: str, actor: Optional[str] = "steward") -> str:
    """Rewrite the definition of an existing term.

    Args:
        uri:        Term URI.
        definition: The new definition text. Should be at least 10 words
                    and must not contain the term label (circular definition).
        actor:      Your name as the steward making the edit.
    """
    result = _patch(f"/terms/{uri}/edit", {
        "definition": definition,
        "actor": actor,
    })
    label = result.get("preferred_label", uri)
    version = result.get("version", "—")
    return f"Definition updated for '{label}'. Now at version v{version}."


@mcp.tool()
def get_taxonomy_concepts(scheme: Optional[str] = None) -> str:
    """List all concepts in the OntoBridge local ontology (103 concepts, 10 schemes).

    Useful for understanding what taxonomy categories are available,
    or for mapping terms to the ontology when building Dawiso packages.

    Args:
        scheme: Optional scheme name to filter by (e.g. 'Compliance', 'Risk',
                'Organisation'). Omit to list all schemes.
    """
    concepts = _get("/stats/concepts")
    if scheme:
        concepts = [c for c in concepts if scheme.lower() in (c.get("scheme_label") or "").lower()]
    if not concepts:
        return f"No concepts found for scheme '{scheme}'."

    # Group by scheme
    grouped: dict[str, list] = {}
    for c in concepts:
        s = c.get("scheme_label") or "Uncategorised"
        grouped.setdefault(s, []).append(c["pref_label"])

    lines = [f"{len(concepts)} concept(s) across {len(grouped)} scheme(s):\n"]
    for scheme_name, labels in sorted(grouped.items()):
        lines.append(f"**{scheme_name}** ({len(labels)})")
        lines.append("  " + ", ".join(sorted(labels)))
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def get_known_verbs() -> str:
    """List the known semantic relation verbs defined in the OntoBridge ontology.

    These are the verbs the Relations agent recognises and maps to formal
    OWL ObjectProperties (e.g. 'governs', 'holds', 'requires', 'triggers').
    Use these when adding semantic relations to a term manually.
    """
    verbs = _get("/stats/verbs")
    return "Known relation verbs:\n" + ", ".join(verbs)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "0"))
    if port:
        # HTTP/SSE mode — for inspector testing and GCP deployment
        print(f"Starting OntoBridge MCP server (SSE) on port {port} -> {BASE_URL}")
        mcp.run(transport="sse", port=port)
    else:
        # STDIO mode — for Claude desktop / Claude Code
        print(f"Starting OntoBridge MCP server (STDIO) -> {BASE_URL}")
        mcp.run(transport="stdio")
