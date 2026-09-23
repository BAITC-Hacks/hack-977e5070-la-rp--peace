"""Stage 4.1 over HTTP: data inserted directly, re-run queued, report and grouped pairs."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from collision_support import GOOD_EXPLANATION, CollisionDoc, ScriptedEmbedder, ScriptedVerifier
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.api import app as app_module
from la_rp_peace.api.app import create_app
from la_rp_peace.config import Settings
from la_rp_peace.embeddings import Embedder

FINISHED = {"done", "needs_review", "failed"}
VECTORS = {"ведёт реестр договоров": [1.0, 0.0], "ведёт реестр всех договоров": [1.0, 0.0], "визирует": [0.0, 1.0]}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}",
        openai_api_key=None,
        openai_model=None,
    )


def _embedder(embedder: Embedder | None) -> Any:
    return lambda _settings: embedder


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(app_module, "_default_embedder", _embedder(ScriptedEmbedder(VECTORS)))
    with TestClient(create_app(_settings(tmp_path), model=ScriptedVerifier())) as test_client:
        yield test_client


def _seed(client: TestClient) -> tuple[int, dict[str, int]]:
    factory: sessionmaker[Session] = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session:
        doc = CollisionDoc(session)
        parent = doc.entity("Юридический отдел", "department")
        first = doc.entity("Юрист 1", "position", parent)
        second = doc.entity("Юрист 2", "position", parent)
        records = {
            "first": doc.record(first, "ведёт реестр договоров"),
            "second": doc.record(second, "ведёт реестр всех договоров"),
            "other": doc.record(second, "визирует"),
        }
        session.commit()
        return doc.id, records | {"first_entity": first, "parent": parent}


def _wait(client: TestClient, path: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(path).json()
        if body["collisions_status"] in FINISHED:
            return body
        time.sleep(0.05)
    raise AssertionError(f"{path} did not finish")


def test_collisions_end_to_end(client: TestClient) -> None:
    document_id, ids = _seed(client)

    queued = client.post(f"/api/documents/{document_id}/collisions")
    assert queued.status_code == 202
    assert queued.json() == {"document_id": document_id, "collisions_status": "running"}
    report = _wait(client, f"/api/documents/{document_id}/collision-report")
    body = client.get(f"/api/documents/{document_id}/collisions").json()

    assert report["collisions_status"] == "needs_review"
    counts = ["compared_records", "compared_views", "pairs_sent", "errors"]
    coverage = ["local_pairs", "local_above", "category_pairs", "category_above"]
    assert [report[name] for name in counts] == [3, 0, 1, 0]
    assert [report[name] for name in coverage] == [2, 1, 2, 1]
    assert report["verdicts"] == {"collision": 1, "no_collision": 0, "insufficient_data": 0}
    assert (report["threshold"], report["metric"], report["embedding_model"]) == (0.75, "cosine", "fake-embedding")
    assert (body["no_collision"], body["insufficient_data"], body["errors"]) == ([], [], [])
    [pair] = body["collision"]
    assert pair["bases"] == ["local", "category"]
    assert pair["explanation"] == GOOD_EXPLANATION
    assert pair["side_a"]["record_id"] == ids["first"]
    assert pair["side_a"]["participants"][0]["name"] == "Юрист 1"
    assert pair["side_a"]["participants"][0]["parent_name"] == "Юридический отдел"
    assert pair["side_b"]["formulation"] == "ведёт реестр всех договоров"
    assert pair["side_a"]["sources"][0]["quote"] == "ведёт реестр договоров"
    assert [source["supports"] for source in pair["sources"]] == [["side_a"], ["side_b"]]
    assert pair["sources"][0]["path"].startswith("п. ")


def test_unknown_document_is_404(client: TestClient) -> None:
    assert client.get("/api/documents/999/collisions").status_code == 404
    assert client.get("/api/documents/999/collision-report").status_code == 404
    assert client.post("/api/documents/999/collisions").status_code == 404


def test_report_before_any_run(client: TestClient) -> None:
    document_id, _ = _seed(client)

    report = client.get(f"/api/documents/{document_id}/collision-report").json()

    assert (report["collisions_status"], report["threshold"], report["pairs_sent"]) == ("not_started", None, 0)


def test_rerun_is_unavailable_without_model_or_embeddings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_default_embedder", _embedder(None))
    with TestClient(create_app(_settings(tmp_path), model=ScriptedVerifier())) as without_embeddings:
        document_id, _ = _seed(without_embeddings)
        assert without_embeddings.post(f"/api/documents/{document_id}/collisions").status_code == 503
        report = without_embeddings.get(f"/api/documents/{document_id}/collision-report").json()
        assert report["collisions_status"] == "not_started"
    with TestClient(create_app(_settings(tmp_path))) as without_model:
        assert without_model.post(f"/api/documents/{document_id}/collisions").status_code == 503
