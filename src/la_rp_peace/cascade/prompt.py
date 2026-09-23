"""What the verification model sees (methodology 4.2 §4): the rules and one question per proposed link."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from la_rp_peace.cascade.groups import entity_of
from la_rp_peace.cascade.matching import Choice
from la_rp_peace.models import ActivityRecord, Entity

SYSTEM_PROMPT = """\
Вы проверяете каскадирование задач и функций внутри одного внутреннего документа организации.

Каждый вопрос — одна предложенная связь внутри группы «организационный объект уровня N и его
непосредственный исполнитель уровня N+1»: родительская задача или функция объекта N и дочерняя
задача или функция исполнителя. Родитель выбран автоматически как лучший кандидат по сходству
эмбеддингов; сходство — не вероятность правильности связи.

Решите только одно: действительно ли дочернее действие обеспечивает выполнение родительской задачи
или функции с учётом предмета, результата, условий, сроков и ролей участников.
- confirmed — дочернее действие выполняет, обеспечивает или является способом выполнения
  родительской задачи или функции (разные действия могут быть связаны как задача и способ её
  выполнения).
- rejected — дочернее действие относится к другому предмету или результату, либо это другое
  действие над тем же предметом: подготовка, согласование, утверждение и контроль не
  взаимозаменяемы.

Опирайтесь только на приведённые записи и цитаты документа. Не предлагайте другого родителя,
не добавляйте функции и не делайте выводов о превышении полномочий.

Ответ — JSON-объект, ровно один ответ на каждый question_id, без других полей:
{"answers": [{"question_id": "q12", "verdict": "confirmed", "explanation": "кратко, до 300 символов"}]}
verdict — только "confirmed" или "rejected"; explanation необязательно.
"""


@dataclass(frozen=True, slots=True)
class Citation:
    """A verbatim quote of a record with the node it comes from."""

    node_id: int
    path: str
    quote: str


def question_id(child_record_id: int) -> str:
    """Return the question id of a child function's link (one question per child function)."""
    return f"q{child_record_id}"


def _record_block(
    title: str,
    record: ActivityRecord,
    entity: Entity,
    citations: Sequence[Citation],
) -> list[str]:
    lines = [
        f"{title} (запись {record.id})",
        f"Объект: {entity.name} ({entity.category}, в документе: {entity.entity_type})",
        f"Вид положения: {record.record_type}",
        f"Формулировка: {record.formulation}",
        f"Участие: {record.participation}; участники: {record.participant_designation}",
        f"Конкретность: {record.specificity}",
    ]
    optional = [("Условие", record.condition), ("Срок", record.deadline), ("Периодичность", record.periodicity)]
    lines += [f"{label}: {value}" for label, value in optional if value]
    lines.append("Цитаты документа:")
    lines += [f"- [node {item.node_id}] {item.path}: «{item.quote}»" for item in citations]
    return lines


def render_question(
    choice: Choice,
    parent: ActivityRecord,
    entities: Mapping[int, Entity],
    citations: Mapping[int, Sequence[Citation]],
    embedding_model: str,
) -> str:
    """Render one question about the proposed link of ``choice``.

    Args:
        choice: The child function and its single best candidate.
        parent: The candidate parent function.
        entities: Entities of the document by id.
        citations: Verbatim quotes by record id.
        embedding_model: Model of the similarity score, shown with it.

    Returns:
        The question text (the question id is added by the batching).

    Raises:
        ValueError: If the child function has no score or no entity.
    """
    group_entity = choice.group.entity
    child = choice.child
    if choice.similarity is None:
        raise ValueError("Only a scored child function can be verified")
    child_entity = entities[entity_of(child)]
    lines = [
        f"Группа: «{group_entity.name}» ({group_entity.category}) и его непосредственный исполнитель "
        f"«{child_entity.name}» ({child_entity.category}).",
        f"Сходство эмбеддингов (cosine, {embedding_model}): {choice.similarity:.4f}",
        "",
    ]
    lines += _record_block("Родительская функция", parent, group_entity, citations.get(parent.id, ()))
    lines.append("")
    lines += _record_block("Дочерняя функция", child, child_entity, citations.get(child.id, ()))
    return "\n".join(lines)
