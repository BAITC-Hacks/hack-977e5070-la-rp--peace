from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from la_rp_peace.api.app import create_app
from la_rp_peace.config import Settings

EDITION_9 = (
    Path(__file__).resolve().parent.parent / "test_data" / "Положение_о_внутреннем_аудите_редакция_9_обезличено.docx"
)
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", max_upload_mb=1)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload(client: TestClient, doc_set: str = "after") -> dict[str, object]:
    response = client.post(
        "/api/documents",
        data={"set": doc_set},
        files={"file": (EDITION_9.name, EDITION_9.read_bytes(), DOCX_TYPE)},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_upload_returns_document_metadata(client: TestClient) -> None:
    document = _upload(client)

    assert document["set"] == "after"
    assert document["doc_type"] == "unit_regulation"
    assert document["format"] == "docx"
    assert document["size"] == EDITION_9.stat().st_size
    assert isinstance(document["clause_count"], int)
    assert document["clause_count"] > 400


def test_clauses_form_a_tree(client: TestClient) -> None:
    document = _upload(client)

    clauses = client.get(f"/api/documents/{document['id']}/clauses").json()

    assert len(clauses) == document["clause_count"]
    by_id = {clause["id"]: clause for clause in clauses}
    item = next(clause for clause in clauses if clause["anchor"] == "п. 3.4 «а»")
    assert by_id[item["parent_id"]]["number"] == "3.4"
    assert item["paragraph_index"] is not None


def test_list_filters_by_set(client: TestClient) -> None:
    _upload(client, "before")
    _upload(client, "after")

    assert len(client.get("/api/documents").json()) == 2
    assert [doc["set"] for doc in client.get("/api/documents", params={"set": "before"}).json()] == ["before"]


def test_patch_overrides_doc_type(client: TestClient) -> None:
    document = _upload(client)

    response = client.patch(f"/api/documents/{document['id']}", json={"doc_type": "job_description"})

    assert response.status_code == 200
    assert client.get(f"/api/documents/{document['id']}").json()["doc_type"] == "job_description"


def test_download_returns_original_bytes(client: TestClient) -> None:
    document = _upload(client)

    response = client.get(f"/api/documents/{document['id']}/file")

    assert response.content == EDITION_9.read_bytes()
    assert response.headers["content-type"] == DOCX_TYPE
    assert quote(EDITION_9.name) in response.headers["content-disposition"]


def test_delete_removes_document_and_clauses(client: TestClient) -> None:
    document = _upload(client)

    assert client.delete(f"/api/documents/{document['id']}").status_code == 204
    assert client.get(f"/api/documents/{document['id']}").status_code == 404
    assert client.get(f"/api/documents/{document['id']}/clauses").status_code == 404


def test_legacy_format_is_rejected(client: TestClient) -> None:
    response = client.post("/api/documents", data={"set": "before"}, files={"file": ("old.doc", b"\xd0\xcf", "x")})

    assert response.status_code == 415
    assert ".docx" in response.json()["detail"]


def test_oversized_upload_is_rejected(client: TestClient) -> None:
    payload = b"%PDF" + b"0" * (1024 * 1024)

    response = client.post("/api/documents", data={"set": "before"}, files={"file": ("big.pdf", payload, "x")})

    assert response.status_code == 413


def test_corrupt_file_is_unprocessable(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        data={"set": "before"},
        files={"file": ("broken.docx", b"PK\x03\x04garbage", DOCX_TYPE)},
    )

    assert response.status_code == 422
    assert client.get("/api/documents").json() == []


def test_unknown_set_is_a_validation_error(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        data={"set": "during"},
        files={"file": (EDITION_9.name, EDITION_9.read_bytes(), DOCX_TYPE)},
    )

    assert response.status_code == 422


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
