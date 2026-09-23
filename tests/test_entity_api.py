import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import edition_path
from entities_support import ScriptedModel, ed9_general, ed9_structure
from fastapi.testclient import TestClient

from la_rp_peace.api.app import create_app
from la_rp_peace.config import Settings

STAGE_FINISHED = {"done", "needs_review", "failed"}


def _settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}", max_upload_mb=1)


@pytest.fixture
def model() -> ScriptedModel:
    return ScriptedModel([ed9_general, ed9_structure])


@pytest.fixture
def client(tmp_path: Path, model: ScriptedModel) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path), model=model)) as test_client:
        yield test_client


def _wait_entities(client: TestClient, document_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        document: dict[str, Any] = client.get(f"/api/documents/{document_id}").json()
        if document["entities_status"] in STAGE_FINISHED:
            return document
        time.sleep(0.1)
    raise AssertionError(f"entities of document {document_id} not finished")


def _upload_ed9(client: TestClient) -> dict[str, Any]:
    path = edition_path(9)
    response = client.post("/api/documents", data={"set": "after"}, files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 202, response.text
    assert response.json()["entities_status"] in {"not_started", "running", *STAGE_FINISHED}
    return _wait_entities(client, response.json()["id"])


def test_upload_chains_stage_2_and_exposes_entities(client: TestClient) -> None:
    document = _upload_ed9(client)
    entities = client.get(f"/api/documents/{document['id']}/entities").json()

    assert (document["parse_status"], document["entities_status"]) == ("validated", "done")
    by_id = {entity["id"]: entity for entity in entities}
    auditors = [entity for entity in entities if entity["name"] == "Аудитор"]
    assert [by_id[auditor["parent_id"]]["aliases"] for auditor in auditors] == [["ДИТААД"], ["ДОА"]]
    parent_source = next(source for source in auditors[0]["sources"] if source["supports"] == ["parent"])
    assert parent_source["path"] == "Разд. 3 «Структура и организация работы внутреннего аудита» › п. 3.6"
    assert parent_source["location"] == {"paragraph": 112}
    assert parent_source["quote"] == "работники ДИТААД в соответствии со штатным расписанием"
    nodes = {node["id"]: node for node in client.get(f"/api/documents/{document['id']}/nodes").json()}
    context = nodes[parent_source["node_id"]]["text"]
    assert context[parent_source["start"] : parent_source["end"]] == parent_source["quote"]
    assert all(entity["review_status"] == "checked" for entity in entities)


def test_relations_and_report(client: TestClient) -> None:
    document = _upload_ed9(client)
    relations = client.get(f"/api/documents/{document['id']}/entity-relations").json()
    report = client.get(f"/api/documents/{document['id']}/entity-report").json()

    assert {relation["relation_type"] for relation in relations} == {"reports_to", "functional_subordination"}
    assert all(relation["sources"] and relation["sources"][0]["supports"] == ["relation"] for relation in relations)
    assert report["entities_status"] == "done"
    assert {block["status"] for block in report["blocks"]} == {"found", "none"}
    assert report["blocks"][0]["path"].startswith("служебный блок")
    assert report["issues"] == []


def test_rerun_is_queued_and_replaces_results(client: TestClient, model: ScriptedModel) -> None:
    document = _upload_ed9(client)
    before = client.get(f"/api/documents/{document['id']}/entities").json()
    calls = len(model.conversations)

    response = client.post(f"/api/documents/{document['id']}/entities")
    assert (response.status_code, response.json()["entities_status"]) == (202, "running")
    rerun = _wait_entities(client, document["id"])
    after = client.get(f"/api/documents/{document['id']}/entities").json()

    assert rerun["entities_status"] == "done"
    assert len(model.conversations) > calls
    assert [entity["name"] for entity in after] == [entity["name"] for entity in before]
    assert client.post("/api/documents/999/entities").status_code == 404


def test_rerun_needs_a_tree(client: TestClient) -> None:
    response = client.post("/api/documents", data={"set": "before"}, files={"file": ("broken.docx", b"PK\x03\x04x")})
    document_id = response.json()["id"]
    deadline = time.monotonic() + 30
    while client.get(f"/api/documents/{document_id}").json()["parse_status"] == "pending":
        assert time.monotonic() < deadline
        time.sleep(0.1)

    assert client.post(f"/api/documents/{document_id}/entities").status_code == 409
    assert client.get(f"/api/documents/{document_id}").json()["entities_status"] == "not_started"


def test_rerun_needs_a_model(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"openai_api_key": None, "openai_model": None})
    with TestClient(create_app(settings, model=None)) as client:
        assert client.post("/api/documents/1/entities").status_code == 503
        assert client.get("/api/documents/1/entities").status_code == 404
