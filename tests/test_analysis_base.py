import json
from collections.abc import Sequence
from typing import Any

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.db import make_engine
from la_rp_peace.embeddings import ActivityText, activity_text, cosine_matrix, embed_texts
from la_rp_peace.llm import ChatModelError, Message
from la_rp_peace.models import EmbeddingCache, create_schema
from la_rp_peace.verification import Answer, Question, ask_in_batches


class CountingEmbedder:
    model = "fake-embedding"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), 1.0, float(sum(map(ord, text)) % 7)] for text in texts]


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return sessionmaker(engine)()


def test_cosine_scores_are_exact() -> None:
    left = np.array([[1.0, 0.0], [1.0, 1.0]])
    right = np.array([[1.0, 0.0], [0.0, 2.0]])

    scores = cosine_matrix(left, right)

    assert scores[0, 0] == pytest.approx(1.0)
    assert scores[0, 1] == pytest.approx(0.0)
    assert scores[1, 0] == pytest.approx(1 / np.sqrt(2))


def test_embeddings_are_cached_by_exact_text(session: Session) -> None:
    embedder = CountingEmbedder()

    first = embed_texts(session, embedder, ["а", "б", "а"])
    session.commit()
    second = embed_texts(session, embedder, ["б", "в"])

    assert embedder.calls == [["а", "б"], ["в"]]
    assert first.shape == (3, 3)
    assert np.array_equal(first[1], second[0])
    assert session.scalar(select(func.count()).select_from(EmbeddingCache)) == 3


def test_activity_text_includes_context_fields() -> None:
    text = activity_text(
        ActivityText(
            "Главный аудитор",
            "position",
            "duty",
            "представляет отчёты",
            "individual",
            "Главный аудитор",
            periodicity="ежеквартально",
        ),
    )

    assert "Объект: Главный аудитор (position)" in text
    assert "Периодичность: ежеквартально" in text
    assert "Условие" not in text


class ScriptedVerifier:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.requests: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        self.requests.append(list(messages))
        reply = self.replies[len(self.requests) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def _ok(_question: Question, answer: Answer) -> list[str]:
    return [] if answer.get("verdict") in ("yes", "no") else [f"недопустимый вердикт {answer.get('verdict')!r}"]


def _answer_all(ids: list[str]) -> dict[str, Any]:
    return {"answers": [{"question_id": qid, "verdict": "yes"} for qid in ids]}


def test_questions_go_in_batches_of_ten() -> None:
    questions = [Question(f"q{n}", f"вопрос {n}") for n in range(23)]
    batches = [[f"q{n}" for n in range(start, min(start + 10, 23))] for start in (0, 10, 20)]
    model = ScriptedVerifier([_answer_all(batch) for batch in batches])

    outcomes = ask_in_batches(model, "system", questions, _ok, retries=1)

    assert len(model.requests) == 3
    assert "Вопросов: 3" in model.requests[2][1].content
    assert all(outcome.answer is not None for outcome in outcomes.values())


def test_missing_invalid_and_foreign_answers_are_asked_again() -> None:
    questions = [Question("q1", "a"), Question("q2", "b"), Question("q3", "c")]
    first = {
        "answers": [
            {"question_id": "q1", "verdict": "yes"},
            {"question_id": "q2", "verdict": "maybe"},
            {"question_id": "zzz", "verdict": "yes"},
        ]
    }
    second = {"answers": [{"question_id": "q2", "verdict": "no"}, {"question_id": "q3", "verdict": "yes"}]}
    model = ScriptedVerifier([first, second])

    outcomes = ask_in_batches(model, "system", questions, _ok, retries=2)

    feedback = model.requests[1][-1].content
    assert "Посторонний или пустой question_id: 'zzz'" in feedback
    assert "q2: недопустимый вердикт 'maybe'" in feedback
    assert "q3: Нет ответа" in feedback
    assert "q1" not in feedback.split("ТОЛЬКО на эти вопросы")[1]
    assert {qid: outcome.answer["verdict"] for qid, outcome in outcomes.items() if outcome.answer} == {
        "q1": "yes",
        "q2": "no",
        "q3": "yes",
    }
    assert outcomes["q1"].attempts == 1
    assert outcomes["q2"].attempts == 2


def test_unanswered_questions_end_as_errors_not_verdicts() -> None:
    questions = [Question("q1", "a"), Question("q2", "b")]
    duplicate = {
        "answers": [
            {"question_id": "q1", "verdict": "yes"},
            {"question_id": "q2", "verdict": "yes"},
            {"question_id": "q2", "verdict": "no"},
        ]
    }
    model = ScriptedVerifier([duplicate, "not json", {"answers": []}])

    outcomes = ask_in_batches(model, "system", questions, _ok, retries=2)

    assert outcomes["q1"].answer == {"question_id": "q1", "verdict": "yes"}
    assert outcomes["q2"].answer is None
    assert outcomes["q2"].error is not None
    assert "Нет корректного ответа за 3 попыток" in outcomes["q2"].error


def test_model_error_fails_the_batch_without_verdicts() -> None:
    model = ScriptedVerifier([ChatModelError("нет сети")])

    outcomes = ask_in_batches(model, "system", [Question("q1", "a")], _ok, retries=2)

    assert outcomes["q1"].answer is None
    assert "нет сети" in (outcomes["q1"].error or "")


def test_question_ids_must_be_unique() -> None:
    with pytest.raises(ValueError, match="unique"):
        ask_in_batches(ScriptedVerifier([]), "system", [Question("q", "a"), Question("q", "b")], _ok, retries=0)
