from __future__ import annotations

from ontobridge.agents.fibo.loader import FiboIndex
from ontobridge.models.fibo import FIBOMatch


class FiboMatcher:
    def __init__(self, index: FiboIndex) -> None:
        self.index = index

    def match(self, label: str | None, definition: str | None = None) -> FIBOMatch | None:
        if not label or not label.strip():
            return None

        normalized = FiboIndex.normalize_label(label)
        uris = self.index.uri_by_label.get(normalized)
        if not uris:
            return None

        uri = sorted(uris)[0]
        expected_definition = self.index.uri_to_definition.get(uri)
        alt_labels = self.index.alt_labels_by_uri.get(uri, [])

        return FIBOMatch(
            uri=uri,
            expected_definition=expected_definition,
            alt_labels=list(alt_labels),
        )
