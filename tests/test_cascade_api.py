"""Stage 4.2 over HTTP: re-run through the queue, the cascade with chains and findings, the report."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cascade_support import DocumentBuilder, FakeEmbedder, ScriptedVerifier, basis, exact_child
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.api.app import create_app
from la_rp_peace.cascade.pipeline import CascadeStage
from la_rp_peace.config import Settings
from la_rp_peace.ingestion.pipeline import ParsingQueue

FINISHED = {"done", "needs_review", "failed"}
VECTORS = {
    "Задача департамента": basis(0),
    "Вторая задача департамента": basis(1),
    "Функция отдела": exact_child({0: 0.9}),
    "Действие аудитора": exact_child({0: 0.88}),
    "Отчёт отдела": exact_child({0: 0.3, 1: 0.2}),
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}",
        openai_api_key=None,
        openai_model=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _factory(client: TestClient) -> sessionmaker[Session]:
    factory: sessionmaker[Session] = client.app.state.session_factory  # type: ignore[attr-defined]
    return factory


def _document(client: TestClient) -> tuple[int, dict[str, int]]:
    with _factory(client)() as session:
        builder = DocumentBuilder(session)
        department = builder.entity("Департамент аудита")
        division = builder.entity("Отдел проверок", department, category="division")
        auditor = builder.entity("Аудитор отдела", division, category="position")
        ids = {
            "task": builder.record(department, "Задача департамента", "task").id,
            "second": builder.record(department, "Вторая задача департамента", "task").id,
            "function": builder.record(division, "Функция отдела").id,
            "report": builder.record(division, "Отчёт отдела", "duty").id,
            "action": builder.record(auditor, "Действие аудитора", "duty").id,
            "loose": builder.record(None, "Функция без исполнителя").id,
        }
        session.commit()
        return builder.id, ids


def _wait(client: TestClient, path: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(path).json()
        if body["cascade_status"] in FINISHED:
            return body
        time.sleep(0.05)
    raise AssertionError(f"{path} did not finish")


def test_cascade_end_to_end(client: TestClient) -> None:
    document_id, ids = _document(client)
    queue = ParsingQueue(
        _factory(client),
        ScriptedVerifier(),
        max_chars=1000,
        retries=0,
        workers=1,
        stages=[CascadeStage(ScriptedVerifier(), FakeEmbedder(VECTORS), retries=0)],
    )
    client.app.state.parsing_queue = queue  # type: ignore[attr-defined]
    try:
        queued = client.post(f"/api/documents/{document_id}/cascade")
        assert queued.status_code == 202
        assert queued.json() == {"document_id": document_id, "cascade_status": "running"}
        report = _wait(client, f"/api/documents/{document_id}/cascade-report")
    finally:
        queue.shutdown()
    cascade = client.get(f"/api/documents/{document_id}/cascade").json()

    assert report["cascade_status"] == "needs_review"
    assert (report["groups"], report["links"]) == (2, 3)
    assert report["links_by_status"] == {"accepted": 2, "not_found": 1}
    assert report["links_by_decision"] == {"auto": 2, "none": 1}
    # «Отчёт отдела» has no basis above and, as a division function, no executor below either.
    assert report["findings_by_kind"] == {"child_without_parent": 1, "parent_without_children": 2}
    assert report["final_anomalies"] == 3
    assert report["excluded_record_ids"] == [ids["loose"]]

    assert [group["entity"]["name"] for group in cascade["groups"]] == ["Департамент аудита", "Отдел проверок"]
    first = cascade["groups"][0]
    assert [child["name"] for child in first["children"]] == ["Отдел проверок"]
    assert [record["id"] for record in first["parent_functions"]] == [ids["task"], ids["second"]]
    [chain] = cascade["chains"]
    assert [record["formulation"] for record in chain] == [
        "Задача департамента",
        "Функция отдела",
        "Действие аудитора",
    ]
    assert [record["entity_name"] for record in chain] == ["Департамент аудита", "Отдел проверок", "Аудитор отдела"]
    source = chain[0]["sources"][0]
    assert (source["path"], source["quote"]) == ("п. 1.", "Задача департамента")
    labels = [
        (finding["record"]["id"], finding["label"], finding["final"], finding["entity"]["name"])
        for finding in cascade["findings"]
    ]
    assert labels == [
        (ids["report"], "Основание не найдено", True, "Отдел проверок"),
        (ids["second"], "Исполнитель не найден", True, "Департамент аудита"),
        (ids["report"], "Исполнитель не найден", True, "Отдел проверок"),
    ]
    assert cascade["auto_accept_above"] == 0.85
    assert cascade["verify_above"] == 0.5


def test_missing_document_and_missing_queue(client: TestClient) -> None:
    document_id, _ids = _document(client)

    assert client.get("/api/documents/999/cascade").status_code == 404
    assert client.get("/api/documents/999/cascade-report").status_code == 404
    assert client.post("/api/documents/999/cascade").status_code == 404
    assert client.post(f"/api/documents/{document_id}/cascade").status_code == 503
    empty = client.get(f"/api/documents/{document_id}/cascade").json()
    assert (empty["cascade_status"], empty["groups"], empty["chains"], empty["findings"]) == ("not_started", [], [], [])


def test_a_queue_without_the_cascade_stage_keeps_the_status(client: TestClient) -> None:
    document_id, _ids = _document(client)
    queue = ParsingQueue(_factory(client), ScriptedVerifier(), max_chars=1000, retries=0, workers=1)
    client.app.state.parsing_queue = queue  # type: ignore[attr-defined]
    try:
        refused = client.post(f"/api/documents/{document_id}/cascade")
    finally:
        queue.shutdown()

    assert refused.status_code == 503
    assert client.get(f"/api/documents/{document_id}/cascade-report").json()["cascade_status"] == "not_started"
