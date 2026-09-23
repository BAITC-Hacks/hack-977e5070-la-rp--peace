from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from la_rp_peace.api.app import create_app
from la_rp_peace.config import Settings
from la_rp_peace.sources import QuoteNotFoundError, locate_quote

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"
EDITION_8 = TEST_DATA / "Положение_о_внутреннем_аудите_редакция_8_обезличено.docx"
EDITION_9 = TEST_DATA / "Положение_о_внутреннем_аудите_редакция_9_обезличено.docx"
EDITION_9_PDF = TEST_DATA / "converted" / "Положение_о_внутреннем_аудите_редакция_9_обезличено.pdf"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))) as test_client:
        yield test_client


def _clause_id(client: TestClient, path: Path, doc_set: str, anchor: str) -> str:
    document = client.post("/api/documents", data={"set": doc_set}, files={"file": (path.name, path.read_bytes())})
    clauses = client.get(f"/api/documents/{document.json()['id']}/clauses").json()
    clause_id: str = next(clause["id"] for clause in clauses if clause["anchor"] == anchor)
    return clause_id


def _resolve(client: TestClient, clause_id: str, quote: str) -> Any:
    return client.post("/api/sources/resolve", json={"clause_id": clause_id, "quote": quote})


def test_locate_quote_ignores_whitespace_differences() -> None:
    assert locate_quote("3.4. БВА состоит из подразделений:", "БВА  состоит\nиз") == (5, 19)


@pytest.mark.parametrize("quote", ["", "   ", "БВА включает"])
def test_locate_quote_rejects_missing_words(quote: str) -> None:
    with pytest.raises(QuoteNotFoundError):
        locate_quote("3.4. БВА состоит из подразделений:", quote)


def test_new_department_is_traced_to_both_editions(client: TestClient) -> None:
    before_id = _clause_id(client, EDITION_8, "before", "п. 3.4")
    after_id = _clause_id(client, EDITION_9, "after", "п. 3.4 «а»")

    before = _resolve(client, before_id, "БВА состоит из следующих структурных подразделений").json()
    after = _resolve(client, after_id, "Департамент ИТ-аудита и анализа данных (ДИТААД)").json()

    assert before["set"] == "before"
    assert before["document_name"] == EDITION_8.name
    assert before["path"] == "Разд. 3 «Структура и организация работы внутреннего аудита» › п. 3.4"
    assert after["set"] == "after"
    assert after["path"] == "Разд. 3 «Структура и организация работы внутреннего аудита» › п. 3.4 › подп. «а»"
    assert after["context"][after["start"] : after["end"]] == "Департамент ИТ-аудита и анализа данных (ДИТААД)"
    assert after["paragraph_index"] == 103


def test_pdf_source_points_at_its_page(client: TestClient) -> None:
    clause_id = _clause_id(client, EDITION_9_PDF, "after", "п. 3.4 «а»")

    source = _resolve(client, clause_id, "ДИТААД").json()

    assert source["page"] == 6
    assert source["paragraph_index"] is None


def test_paraphrased_quote_is_rejected(client: TestClient) -> None:
    clause_id = _clause_id(client, EDITION_9, "after", "п. 3.4 «а»")

    response = _resolve(client, clause_id, "Департамент ИТ аудита")

    assert response.status_code == 422
    assert "не найдена" in response.json()["detail"]


def test_unknown_clause_is_not_found(client: TestClient) -> None:
    assert _resolve(client, "missing", "текст").status_code == 404
    assert client.get("/api/clauses/missing").status_code == 404


def test_clause_lookup_quotes_the_whole_clause(client: TestClient) -> None:
    clause_id = _clause_id(client, EDITION_9, "after", "п. 3.4 «б»")

    source = client.get(f"/api/clauses/{clause_id}").json()

    assert source["quote"] == source["context"] == "б. Департамент операционного аудита (ДОА)."
    assert (source["start"], source["end"]) == (0, len(source["context"]))
