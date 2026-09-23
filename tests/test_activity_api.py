"""Stage 3 over HTTP: upload, stage 2 registry inserted directly, re-run, report and records."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from activity_script import ED9_ENTITIES, ScriptedModel, add_entities
from conftest import edition_path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from test_activities import ED9_HANDLERS

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
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path), model=ScriptedModel(ED9_HANDLERS))) as test_client:
        yield test_client


def _wait(client: TestClient, path: str, field: str, finished: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(path).json()
        if body[field] in finished:
            return body
        time.sleep(0.1)
    raise AssertionError(f"{path} did not finish")


def _parsed_with_entities(client: TestClient) -> tuple[int, dict[str, int]]:
    path = edition_path(9)
    uploaded = client.post("/api/documents", data={"set": "after"}, files={"file": (path.name, path.read_bytes())})
    document_id: int = uploaded.json()["id"]
    document = _wait(client, f"/api/documents/{document_id}", "parse_status", {"validated", "needs_review"})
    # Stage 2 is not part of this branch: the pipeline skipped stage 3 and left it not_started.
    assert document["activities_status"] == "not_started"
    factory: sessionmaker[Session] = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session:
        entities = add_entities(session, document_id, ED9_ENTITIES)
    return document_id, entities


def test_activities_end_to_end(client: TestClient) -> None:
    document_id, entities = _parsed_with_entities(client)

    queued = client.post(f"/api/documents/{document_id}/activities")
    assert queued.status_code == 202
    report = _wait(client, f"/api/documents/{document_id}/activity-report", "activities_status", FINISHED)
    records = client.get(f"/api/documents/{document_id}/activities").json()

    assert report["activities_status"] == "needs_review"
    assert report["record_count"] == len(records) == 8
    assert {block["status"] for block in report["blocks"]} == {"found", "none"}
    assert [issue["issue_type"] for issue in report["issues"]] == ["unresolved_entity"]
    report_duty = next(record for record in records if record["formulation"].startswith("Главный аудитор представляет"))
    (chief,) = report_duty["bindings"]
    assert (chief["entity_id"], chief["entity_name"]) == (entities["Главный аудитор"], "Главный аудитор")
    assert chief["sources"][0]["path"] == "Разд. 5 «Права и обязанности» › «Главный аудитор:»"
    periodicity = next(item for item in report_duty["sources"] if item["supports"] == ["periodicity"])
    assert periodicity["path"].endswith("п. 5.1.6")
    assert "paragraph" in periodicity["location"]
    assert periodicity["quote"] == "на ежеквартальной основе и по итогам года"
    assert client.get(f"/api/documents/{document_id}").json()["activities_status"] == "needs_review"


def test_missing_document_and_missing_model(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get("/api/documents/999/activities").status_code == 404
        assert client.get("/api/documents/999/activity-report").status_code == 404
        assert client.post("/api/documents/999/activities").status_code == 404


def test_rerun_without_model_is_unavailable(client: TestClient) -> None:
    document_id, _ = _parsed_with_entities(client)
    database = client.app.state.settings.database_url  # type: ignore[attr-defined]
    settings = Settings(database_url=database, openai_api_key=None, openai_model=None)

    with TestClient(create_app(settings)) as offline:
        assert offline.post(f"/api/documents/{document_id}/activities").status_code == 503
