"""Stage 3 over HTTP: upload, stage 2 registry inserted directly, re-run, report and records."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from activity_script import ED9_ENTITIES, ScriptedModel, add_entities, node_texts
from conftest import edition_path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from test_activities import ED9_HANDLERS, ED9_RECORDS

from la_rp_peace.api.app import create_app
from la_rp_peace.config import Settings

FINISHED = {"done", "needs_review", "failed"}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}",
        openai_api_key=None,
        openai_model=None,
    )


@pytest.fixture
def model() -> ScriptedModel:
    return ScriptedModel(ED9_HANDLERS)


@pytest.fixture
def client(tmp_path: Path, model: ScriptedModel) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path), model=model)) as test_client:
        yield test_client


def _wait(client: TestClient, path: str, field: str, finished: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(path).json()
        if body[field] in finished:
            return body
        time.sleep(0.1)
    raise AssertionError(f"{path} did not finish")


def _parsed_with_entities(client: TestClient, model: ScriptedModel) -> tuple[int, dict[str, int]]:
    path = edition_path(9)
    uploaded = client.post("/api/documents", data={"set": "after"}, files={"file": (path.name, path.read_bytes())})
    document_id: int = uploaded.json()["id"]
    _wait(client, f"/api/documents/{document_id}", "parse_status", {"validated", "needs_review"})
    # The automatic chain runs stage 2 and then stage 3 with this stage 3 script, which cannot answer
    # stage 2; wait until the whole chain is over before replacing its registry with a known one.
    _wait(client, f"/api/documents/{document_id}", "activities_status", FINISHED)
    factory: sessionmaker[Session] = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session:
        entities = add_entities(session, document_id, ED9_ENTITIES)
        model.document = node_texts(session, document_id)
    return document_id, entities


def test_activities_end_to_end(client: TestClient, model: ScriptedModel) -> None:
    document_id, entities = _parsed_with_entities(client, model)

    queued = client.post(f"/api/documents/{document_id}/activities")
    assert queued.status_code == 202
    report = _wait(client, f"/api/documents/{document_id}/activity-report", "activities_status", FINISHED)
    records = client.get(f"/api/documents/{document_id}/activities").json()

    assert report["activities_status"] == "needs_review"
    assert report["record_count"] == len(records) == ED9_RECORDS
    assert {block["status"] for block in report["blocks"]} == {"found", "none"}
    # 5.7.9 (right and duty), 5.8.2: undisclosed remainder of «работники БВА»; 9.4: authorised worker.
    assert [issue["issue_type"] for issue in report["issues"]] == ["unresolved_entity"] * 4
    report_duty = next(record for record in records if record["formulation"].startswith("Главный аудитор представляет"))
    assert (report_duty["entity_id"], report_duty["entity_name"]) == (entities["Главный аудитор"], "Главный аудитор")
    assert (report_duty["participation"], report_duty["other_participants"]) == ("individual", [])
    chief = next(item for item in report_duty["sources"] if item["supports"] == ["entity"])
    assert chief["path"] == "Разд. 5 «Права и обязанности» › «Главный аудитор:»"
    periodicity = next(item for item in report_duty["sources"] if item["supports"] == ["periodicity"])
    assert periodicity["path"].endswith("п. 5.1.6")
    assert "paragraph" in periodicity["location"]
    assert periodicity["quote"] == "на ежеквартальной основе и по итогам года"
    alternative = [record for record in records if record["participation"] == "alternative"]
    assert [(record["entity_name"], record["designation"]) for record in alternative] == [
        ("Главный аудитор", "Главный аудитор"),
        (None, "уполномоченный им работник"),
    ]
    assert alternative[1]["other_participants"] == [
        {"entity_id": entities["Главный аудитор"], "entity_name": "Главный аудитор"},
    ]
    assert client.get(f"/api/documents/{document_id}").json()["activities_status"] == "needs_review"


def test_missing_document_and_missing_model(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get("/api/documents/999/activities").status_code == 404
        assert client.get("/api/documents/999/activity-report").status_code == 404
        assert client.post("/api/documents/999/activities").status_code == 404


def test_rerun_without_model_is_unavailable(client: TestClient, model: ScriptedModel) -> None:
    document_id, _ = _parsed_with_entities(client, model)
    database = client.app.state.settings.database_url  # type: ignore[attr-defined]
    settings = Settings(database_url=database, openai_api_key=None, openai_model=None)

    with TestClient(create_app(settings)) as offline:
        assert offline.post(f"/api/documents/{document_id}/activities").status_code == 503
