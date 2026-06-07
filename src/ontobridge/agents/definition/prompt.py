from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from ontobridge.models.enrichment import BusinessRule, EnrichedTerm

if TYPE_CHECKING:
    from ontobridge.feedback.models import FeedbackEvent

SYSTEM_PROMPT = """\
You are a business glossary writer for a financial institution.

Given a business term with context, produce:
1. A clear, plain-language definition — minimum 10 words, no unexplained jargon,
   written for a business audience (not technical).
2. 2–3 IF...THEN business rules that govern when and how this term applies.

Return ONLY a valid JSON object — no explanation, no markdown fences.

Output format (strictly):
{
  "definition": "Plain-language definition of the term.",
  "business_rules": [
    {
      "rule_text": "IF <condition> THEN <consequence>.",
      "condition": "IF <condition>",
      "consequence": "THEN <consequence>."
    }
  ]
}\
"""


def build_user_prompt(
    term: EnrichedTerm,
    examples: list[FeedbackEvent] | None = None,
) -> str:
    parts: list[str] = []

    label = term.preferred_label or "(unknown term)"
    parts.append(f"Term: {label}")

    if term.definition:
        parts.append(f"Existing definition (improve this): {term.definition}")

    if term.policy_context:
        best = term.policy_context[0]
        ref = best.document_ref
        if best.section:
            ref += f" {best.section}"
        parts.append(f"Policy source ({ref}):\n{best.paragraph}")

    if term.taxonomy_placement:
        pl = term.taxonomy_placement
        if pl.domain_prefix:
            parts.append(f"Domain: {pl.domain_prefix}")
        if pl.broader_concept_uri:
            broader = pl.broader_concept_uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            parts.append(f"Broader concept: {broader}")

    if examples:
        lines = "\n".join(
            f'  "{e.term_label}": '
            f'agent wrote "{e.old_value[:100]}{"..." if len(e.old_value) > 100 else ""}" '
            f'→ steward corrected to "{e.new_value[:100]}{"..." if len(e.new_value) > 100 else ""}"'
            for e in examples[:3]
        )
        parts.append(f"Past steward corrections (use as style guide):\n{lines}")

    return "\n\n".join(parts)


def parse_response(response: str) -> dict:
    """Parse LLM response into a dict with 'definition' and 'business_rules'.

    Strips markdown fences and finds the first JSON object in the response.
    Returns {} on any error so the caller can fall back to the original values.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()

    brace = cleaned.find("{")
    if brace > 0:
        cleaned = cleaned[brace:]

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def extract_definition(data: dict, min_words: int = 10) -> str | None:
    """Return the definition string if it meets the minimum word count."""
    definition = str(data.get("definition", "")).strip()
    if len(definition.split()) >= min_words:
        return definition
    return None


def extract_business_rules(data: dict) -> list[BusinessRule]:
    """Convert the 'business_rules' list from the parsed response."""
    raw_rules = data.get("business_rules", [])
    if not isinstance(raw_rules, list):
        return []

    rules: list[BusinessRule] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        rule_text = str(item.get("rule_text", "")).strip()
        if not rule_text:
            continue
        rules.append(
            BusinessRule(
                rule_text=rule_text,
                condition=str(item.get("condition", "")).strip() or None,
                consequence=str(item.get("consequence", "")).strip() or None,
            )
        )
    return rules
