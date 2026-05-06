from __future__ import annotations

import json
import re

from ontobridge.agents.harvester.protocols import ExtractedTerm

SYSTEM_PROMPT = """\
You are a business terminology extractor for a financial institution.

Task: read the provided text and identify distinct business concepts, entities,
and processes that belong in a corporate data glossary.

Rules:
- Extract only domain-specific terms — not generic words like "information" or "process"
- Terms are typically 1–5 words, noun phrases (e.g. "Retail PI Customer", "Credit Check")
- Definition must be at least 10 words, derived directly from the provided text
- Confidence: 0.90 for terms explicitly defined in the text, 0.70–0.85 for terms that
  are clearly mentioned but whose definition must be inferred from context
- Return ONLY a valid JSON array — no explanation, no markdown fences

Output format (strictly):
[{"term": "Term Name", "definition": "Definition sentence from the text.", "confidence": 0.9}]

If no domain-specific business terms are found, return exactly: []\
"""


def build_user_prompt(text: str) -> str:
    return f"Extract business terms from this text:\n\n{text}"


def parse_response(response: str) -> list[dict]:
    """Parse LLM response into a list of raw dicts.

    Strips markdown code fences (``` or ```json) that some models add despite
    instructions.  Returns [] on any JSON error — the pipeline must never crash
    due to a malformed LLM response.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()

    # Some models prepend a short sentence before the JSON array — find the first "["
    bracket = cleaned.find("[")
    if bracket > 0:
        cleaned = cleaned[bracket:]

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def items_to_extracted_terms(items: list[dict]) -> list[ExtractedTerm]:
    """Convert parsed JSON dicts to ExtractedTerm objects.

    Silently skips malformed entries (missing term / definition, bad types).
    """
    results: list[ExtractedTerm] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("term", "")).strip()
        definition = str(item.get("definition", "")).strip()
        if not label or not definition:
            continue
        try:
            confidence = float(item.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.8
        results.append(
            ExtractedTerm(
                candidate_label=label,
                definition=definition,
                confidence=confidence,
            )
        )
    return results
