from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ontobridge.agents.fibo.matcher import FiboRelation
from ontobridge.models.enrichment import EnrichedTerm

if TYPE_CHECKING:
    from ontobridge.feedback.models import FeedbackEvent

SYSTEM_PROMPT = """\
You are a financial ontology expert helping to identify semantic relations for \
banking concepts. Given a term, its definition, its FIBO mapping, and known \
FIBO-derived relations, propose additional domain-specific relations that are \
implied by the business context but not yet captured.

Respond with a JSON array. Each element must have exactly two string fields:
  "verb"   — a short active-voice verb phrase (e.g. "requires", "is assessed by")
  "object" — the related concept name (e.g. "CreditScore", "Mortgage Application")

Return only the JSON array, no explanation. If no additional relations apply, \
return an empty array [].
"""


def build_user_prompt(
    term: EnrichedTerm,
    fibo_relations: list[FiboRelation],
    match_type: str,
    approved: list[FeedbackEvent] | None = None,
    rejected: list[FeedbackEvent] | None = None,
) -> str:
    label = term.preferred_label or "unknown"
    definition = term.definition or "(no definition)"

    fibo_lines = "\n".join(
        f"  - {r.property_label or r.property_uri} → "
        f"{r.range_label or r.range_uri}"
        for r in fibo_relations
    ) or "  (none)"

    context_snippets = "\n".join(
        f"  [{ctx.document_ref}] {ctx.paragraph[:200]}"
        for ctx in term.policy_context[:3]
    ) or "  (none)"

    match_note = {
        "exact": "This term is an exact match to the FIBO concept.",
        "close": "This term is a close match — similar but may have nuances.",
        "broad": "The FIBO concept is broader; this term is a specific subtype.",
        "none": "This term has no FIBO equivalent — derive relations purely from the policy context.",
    }.get(match_type, "")

    feedback_section = ""
    if approved:
        lines = "\n".join(f'  "{e.term_label}" → {e.new_value}' for e in approved[:3])
        feedback_section += f"\nSteward-approved relations (these types are valued):\n{lines}\n"
    if rejected:
        lines = "\n".join(f'  "{e.term_label}" → {e.old_value}' for e in rejected[:3])
        feedback_section += f"\nSteward-rejected relations (avoid proposing these types):\n{lines}\n"

    return f"""\
Term: {label}
Definition: {definition}
FIBO match type: {match_type}. {match_note}

Known FIBO relations for the matched concept:
{fibo_lines}

Policy context snippets:
{context_snippets}
{feedback_section}
Propose additional relations specific to this term's business context \
(do not repeat the FIBO relations listed above):"""


def parse_response(response: str) -> list[dict[str, str]]:
    text = response.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    result: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict):
            verb = str(item.get("verb", "")).strip()
            obj = str(item.get("object", "")).strip()
            if verb and obj:
                result.append({"verb": verb, "object": obj})
    return result
