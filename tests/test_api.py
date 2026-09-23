import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from conftest import RecordedProfiler, edition_path
from fastapi.testclient import TestClient

from la_rp_peace.api.app import create_app
from la_rp_peace.config import Settings

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FINISHED = {"validated", "needs_review"}


@pytest.fixture
def client(tmp_path: Path, edition_profiler: RecordedProfiler) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}", max_upload_mb=1)
    with TestClient(create_app(settings, profiler=edition_profiler)) as test_client:
        yield test_client


def _upload(client: TestClient, path: Path, doc_set: str) -> dict[str, Any]:
    response = client.post("/api/documents", data={"set": doc_set}, files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


def _wait(client: TestClient, document_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        document: dict[str, Any] = client.get(f"/api/documents/{document_id}").json()
        if document["parse_status"] in FINISHED:
            return document
        time.sleep(0.1)
    raise AssertionError(f"document {document_id} still pending")


def _node(client: TestClient, document_id: int, anchor: str) -> dict[str, Any]:
    nodes = client.get(f"/api/documents/{document_id}/nodes").json()
    node: dict[str, Any] = next(node for node in nodes if node["anchor"] == anchor)
    return node


def test_upload_is_parsed_in_the_background(client: TestClient) -> None:
    uploaded = _upload(client, edition_path(8), "before")

    assert uploaded["parse_status"] in ("pending", *FINISHED)
    document = _wait(client, uploaded["id"])
    assert document["parse_status"] == "validated"
    assert document["set"] == "before"
    assert (document["approval_number"], document["approved_on"], document["revision"]) == ("13", "2021-06-25", "8")
    assert document["node_count"] > 500
    assert (document["blocking_issues"], document["other_issues"]) == (0, 1)


def test_nodes_carry_paths_and_locations(client: TestClient) -> None:
    docx = _wait(client, _upload(client, edition_path(9), "after")["id"])
    pdf = _wait(client, _upload(client, edition_path(9, ".pdf"), "after")["id"])

    from_docx = _node(client, docx["id"], "п. 3.4 «а»")
    from_pdf = _node(client, pdf["id"], "п. 3.4 «а»")

    expected_path = "Разд. 3 «Структура и организация работы внутреннего аудита» › п. 3.4 › подп. «а»"
    assert from_docx["path"] == from_pdf["path"] == expected_path
    assert from_docx["location"] == {"paragraph": 103}
    assert from_pdf["location"] == {"page": 6}
    assert from_docx["text"] == "а. Департамент ИТ-аудита и анализа данных (ДИТААД)."


def test_quote_resolves_to_original_text_offsets(client: TestClient) -> None:
    document = _wait(client, _upload(client, edition_path(9), "after")["id"])
    node = _node(client, document["id"], "п. 3.4 «а»")

    source = client.post("/api/sources/resolve", json={"node_id": node["id"], "quote": "ДИТААД"}).json()
    rejected = client.post("/api/sources/resolve", json={"node_id": node["id"], "quote": "ДИТ ААД"})

    assert source["set"] == "after"
    assert source["path"].endswith("п. 3.4 › подп. «а»")
    assert source["context"][source["start"] : source["end"]] == "ДИТААД"
    assert source["source_end"] - source["source_start"] == len("ДИТААД")
    assert rejected.status_code == 422
    assert client.get(f"/api/nodes/{node['id']}").json()["quote"] == node["text"]


def test_issues_and_profile_are_exposed(client: TestClient) -> None:
    document = _wait(client, _upload(client, edition_path(8), "before")["id"])

    issues = client.get(f"/api/documents/{document['id']}/issues").json()
    profile = client.get(f"/api/documents/{document['id']}/profile").json()

    assert [(issue["issue_type"], issue["is_blocking"]) for issue in issues] == [("empty_content", False)]
    assert profile["parsing_profile"]["strategy"] == "numbering"
    assert profile["metadata_evidence"]["approved_on"]["quotes"][0]["text"] == "от «25» июня 2021 года"


def test_list_patch_download_and_delete(client: TestClient) -> None:
    before = _wait(client, _upload(client, edition_path(8), "before")["id"])
    _wait(client, _upload(client, edition_path(9), "after")["id"])

    assert [doc["set"] for doc in client.get("/api/documents", params={"set": "before"}).json()] == ["before"]
    patched = client.patch(f"/api/documents/{before['id']}", json={"document_type": "положение о подразделении"})
    assert patched.json()["document_type"] == "положение о подразделении"
    download = client.get(f"/api/documents/{before['id']}/file")
    assert download.content == edition_path(8).read_bytes()
    assert download.headers["content-type"] == DOCX_TYPE
    assert quote(edition_path(8).name) in download.headers["content-disposition"]
    assert client.delete(f"/api/documents/{before['id']}").status_code == 204
    assert client.get(f"/api/documents/{before['id']}").status_code == 404


def test_rejected_uploads(client: TestClient) -> None:
    legacy = client.post("/api/documents", data={"set": "before"}, files={"file": ("old.doc", b"\xd0\xcf", "x")})
    oversized = client.post(
        "/api/documents",
        data={"set": "before"},
        files={"file": ("big.pdf", b"%PDF" + b"0" * 1024 * 1024, "x")},
    )
    unknown_set = client.post("/api/documents", data={"set": "during"}, files={"file": ("a.docx", b"PK\x03\x04", "x")})

    assert legacy.status_code == 415
    assert oversized.status_code == 413
    assert unknown_set.status_code == 422


def test_corrupt_file_needs_review(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        data={"set": "before"},
        files={"file": ("broken.docx", b"PK\x03\x04garbage", DOCX_TYPE)},
    )

    document = _wait(client, response.json()["id"])
    issues = client.get(f"/api/documents/{document['id']}/issues").json()

    assert document["parse_status"] == "needs_review"
    assert issues[0]["is_blocking"] is True


def test_uploads_are_refused_without_a_model(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}", openai_api_key=None)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/documents",
            data={"set": "before"},
            files={"file": (edition_path(8).name, edition_path(8).read_bytes())},
        )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
