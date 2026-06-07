from __future__ import annotations

from ontobridge.integrations.dawiso import DawisoSyncAgent, DawisoTermInfo
from ontobridge.models import CandidateLabel, EnrichedTerm, HarvestRecord, SourceRef, SourceType, Tier
from ontobridge.pipeline import PipelineRunner
from ontobridge.publisher import InMemoryPublisher


def _harvest() -> HarvestRecord:
    return HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )


def test_dawiso_sync_agent_updates_existing_term():
    class StubPublisher:
        _base = "http://stub.dawiso"
        _headers: dict = {}
        _cookies: dict = {}

        def get_scheme_label(self, term):
            return "Product"

        def _search_domain(self, client, scheme_label: str) -> int | None:
            return 10 if scheme_label == "Product" else None

        def _find_term_with_client(self, client, domain_id, name: str) -> DawisoTermInfo | None:
            if name.casefold() == "existing term":
                return DawisoTermInfo(
                    object_id=101,
                    name="Existing term",
                    alt_labels=["Existing alias"],
                )
            return None

    term = EnrichedTerm.from_harvest(_harvest())
    term.candidate_labels = [
        CandidateLabel(text="New candidate", confidence=0.9),
        CandidateLabel(text="Existing term", confidence=0.8),
    ]
    term.definition = "A test definition."

    agent = DawisoSyncAgent(StubPublisher())
    agent.apply(term)

    assert term.dawiso_object_id == 101
    assert term.dawiso_domain_id == 10
    assert term.dawiso_sync_action == "update"
    assert "Existing alias" in term.dawiso_existing_labels


def test_dawiso_sync_agent_marks_missing_term_as_create():
    class StubPublisher:
        _base = "http://stub.dawiso"
        _headers: dict = {}
        _cookies: dict = {}

        def get_scheme_label(self, term):
            return "Product"

        def _search_domain(self, client, scheme_label: str) -> int | None:
            return 10

        def _find_term_with_client(self, client, domain_id, name: str):
            return None

    term = EnrichedTerm.from_harvest(_harvest())
    term.candidate_labels = [CandidateLabel(text="Brand new term", confidence=0.9)]
    term.definition = "A brand new definition."

    agent = DawisoSyncAgent(StubPublisher())
    agent.apply(term)

    assert term.dawiso_object_id is None
    assert term.dawiso_sync_action == "create"


def test_pipeline_runner_accepts_dawiso_publisher(base_ontology):
    class StubPublisher:
        def get_scheme_label(self, term):
            return "Product"

        def find_domain(self, scheme_label: str) -> int | None:
            return None

        def find_term(self, domain_id: int, name: str):
            return None

    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub, dawiso_publisher=StubPublisher())
    assert runner.dawiso_sync_agent is not None


def test_dawiso_publisher_falls_back_to_synonym_search():
    class StubResponse:
        def __init__(self, data):
            self._data = data
            self.is_success = True

        def json(self):
            return {"data": self._data}

    class StubClient:
        def __init__(self):
            self.calls = []

        def post(self, path, json):
            self.calls.append((path, json))
            if json["filter"]["objectTypeId"] == 22:
                return StubResponse([])
            return StubResponse([
                {
                    "objectId": 123,
                    "objectName": "LTV",
                    "parentObjectId": 456,
                }
            ])

    from ontobridge.integrations.dawiso import DawisoPublisher

    publisher = DawisoPublisher("https://example.com", "jwt", "sess", 166)
    result = publisher._find_term_with_client(StubClient(), 10, "LTV ratio")

    assert result is not None
    assert result.object_id == 456


def test_dawiso_search_domain_reuses_existing_domain_by_name_field():
    class StubResponse:
        def __init__(self, data):
            self._data = data
            self.is_success = True

        def json(self):
            return {"data": self._data}

    class StubClient:
        def post(self, path, json):
            if path == "/api/mr-object/filter":
                return StubResponse([
                    {"objectId": 77, "name": "Product"}
                ])
            raise AssertionError("Unexpected path: %s" % path)

    from ontobridge.integrations.dawiso import DawisoPublisher

    publisher = DawisoPublisher("https://example.com", "jwt", "sess", 166)
    result = publisher._search_domain(StubClient(), "Product")

    assert result == 77


def test_dawiso_publisher_updates_term_with_new_synonyms():
    class StubResponse:
        def __init__(self, data):
            self._data = data
            self.is_success = True

        def json(self):
            return {"data": self._data}

    class StubClient:
        def __init__(self):
            self.posts = []
            self.puts = []

        def post(self, path, json):
            self.posts.append((path, json))
            if path == "/api/mr-object/filter":
                if json["filter"].get("objectTypeId") == 25:
                    if json["filter"].get("parentObjectId") == 200 and json["filter"].get("objectName") == "Existing alias":
                        return StubResponse([
                            {"objectId": 999, "objectName": "Existing alias"}
                        ])
                return StubResponse([])
            if path == "/api/mr-object":
                return StubResponse({"objectId": 123})
            return StubResponse([])

        def put(self, path, json):
            self.puts.append((path, json))
            return StubResponse([])

    from ontobridge.integrations.dawiso import DawisoPublisher

    client = StubClient()
    publisher = DawisoPublisher("https://example.com", "jwt", "sess", 166)
    publisher._update_term(
        client,
        term_id=200,
        definition="Updated definition",
        alt_labels=["Existing alias", "New synonym"],
    )

    assert any(call[0] == "/api/mr-object/200/attribute/27" for call in client.puts)
    assert any(path == "/api/mr-object" and payload.get("name") == "New synonym" for path, payload in client.posts)
    assert not any(path == "/api/mr-object" and payload.get("name") == "Existing alias" for path, payload in client.posts)
