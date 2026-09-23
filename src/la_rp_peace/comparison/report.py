"""Assemble the stage 5.2 result as the frontend ``JobResult`` (``from[] → finding → to[]``)."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.comparison.run import (
    CHANGE_LABELS,
    Candidates,
    Side,
    _norm,
    _short,
    record_sources,
)
from la_rp_peace.models import ActivityRecord, CollisionPair, Entity
from la_rp_peace.verification import Outcome

UNITS = "Подразделения и должности"
DUPLICATION = "Дублирование (после)"


@dataclass(slots=True)
class Report:
    """Blocks and findings being built."""

    blocks: dict[str, dict[str, Any]] = field(default_factory=dict)
    findings: dict[str, dict[str, Any]] = field(default_factory=dict)
    kept: int = 0
    errors: int = 0

    def block(self, title: str) -> dict[str, Any]:
        return self.blocks.setdefault(title, {"title": title, "before": [], "after": [], "changes": []})

    def item(self, title: str, side: str, item_id: str, label: str, status: str | None, clause: str) -> None:
        items = self.block(title)[side]
        if not any(existing["id"] == item_id for existing in items):
            items.append({"id": item_id, "label": label, "status": status, "clause_id": clause})

    def add(self, title: str, finding: dict[str, Any]) -> str:
        finding_id = f"C-{len(self.findings) + 1:03d}"
        finding.update(id=finding_id, block=title, review=None)
        self.findings[finding_id] = finding
        self.block(title)["changes"].append(finding_id)
        return finding_id


def _evidence(
    conclusion: str, method: str, steps: list[dict[str, Any]], confidence: str, **extra: Any
) -> dict[str, Any]:
    return {"conclusion": conclusion, "method": method, "steps": steps, "confidence": confidence, **extra}


def _fact(text: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "fact", "text": text, "sources": sources}


def _inference(text: str) -> dict[str, Any]:
    return {"kind": "inference", "text": text, "sources": []}


# --- entities --------------------------------------------------------------------------------


def entity_findings(report: Report, before: Side, after: Side, pairs: dict[int, tuple[int, float]]) -> None:
    """Units kept, renamed / moved in the structure, present only before or only after."""
    matched_after = {target for target, _ in pairs.values()}
    for entity in before.entities.values():
        item = f"b_e{entity.id}"
        match = pairs.get(entity.id)
        if match is None:
            _only_one_side(report, before, entity, item, "abolished")
            continue
        target = after.entities[match[0]]
        changes = []
        if _norm(target.name) != _norm(entity.name):
            changes.append(f"название: «{entity.name}» → «{target.name}»")
        if _norm(before.parent_name(entity)) != _norm(after.parent_name(target)):
            changes.append(f"принадлежность: «{before.parent_name(entity)}» → «{after.parent_name(target)}»")
        status = "transformed" if changes else "kept"
        report.item(UNITS, "before", item, entity.name, status, f"entity:{entity.id}")
        report.item(UNITS, "after", f"a_e{target.id}", target.name, status, f"entity:{target.id}")
        if changes:
            report.add(
                UNITS,
                {
                    "type": "transformed",
                    "title": f"Изменено: {entity.name}",
                    "desc": "; ".join(changes),
                    "from": [item],
                    "to": [f"a_e{target.id}"],
                    "evidence": _evidence(
                        "Объект сохранился с изменениями: " + "; ".join(changes),
                        "Совпадение названия/сокращения или сходство описаний",
                        [
                            _inference(
                                f"Сопоставление по {'названию' if match[1] >= 0.999 else f'сходству {match[1]:.2f}'}"
                            )
                        ],
                        "high" if match[1] >= 0.999 else "medium",
                    ),
                },
            )
    for entity in after.entities.values():
        if entity.id not in matched_after:
            _only_one_side(report, after, entity, f"a_e{entity.id}", "created")


def _only_one_side(report: Report, side: Side, entity: Entity, item: str, kind: str) -> None:
    column = "before" if side.name == "before" else "after"
    report.item(UNITS, column, item, entity.name, kind, f"entity:{entity.id}")
    where = "«после»" if kind == "abolished" else "«до»"
    report.add(
        UNITS,
        {
            "type": kind,
            "title": ("Только в «до»: " if kind == "abolished" else "Только в «после»: ") + entity.name,
            "desc": f"В документах {where} соответствующий объект не найден; создание или упразднение требует подтверждения.",
            "from": [item] if kind == "abolished" else [],
            "to": [item] if kind == "created" else [],
            "evidence": _evidence(
                f"Изменение представленного состава: объект найден только в одной редакции ({side.name}).",
                "Сопоставление названий, сокращений и описаний объектов обеих сторон",
                [_inference(f"{entity.name} ({entity.category})")],
                "medium",
                checked={"scope": f"Все объекты документов {where}", "threshold": 0.8, "candidates": []},
            ),
        },
    )


# --- activities ------------------------------------------------------------------------------


def _block_for(side: Side, record: ActivityRecord) -> str:
    return side.owner(record)


def _item(report: Report, title: str, side: Side, record: ActivityRecord, status: str | None) -> str:
    prefix = "b" if side.name == "before" else "a"
    item = f"{prefix}_r{record.id}"
    column = "before" if side.name == "before" else "after"
    report.item(
        title, column, item, f"{side.owner(record)}: {_short(record.formulation)}", status, f"record:{record.id}"
    )
    return item


def activity_findings(
    report: Report, before: Side, after: Side, items: list[Candidates], outcomes: dict[str, Outcome]
) -> set[int]:
    """One finding per before record that changed, was lost or could not be verified; returns matched after ids."""
    matched_after: set[int] = set()
    by_id = {record.id: record for record in after.records}
    for item in items:
        record = item.record
        title = _block_for(before, record)
        outcome = outcomes.get(f"q{record.id}")
        accepted = _accepted(outcome)
        matched_after |= {int(ref[1:]) for ref, _ in accepted}
        if item.after and outcome is not None and outcome.answer is None:
            report.errors += 1
            _needs_review(report, title, before, record, outcome.error or "нет ответа")
            continue
        if not accepted:
            _loss(report, title, before, record, item)
            continue
        changes = sorted({flag for _, match in accepted for flag in match.get("changes", []) if flag in CHANGE_LABELS})
        full = outcome is not None and outcome.answer is not None and outcome.answer.get("coverage") == "full"
        if full and not changes:
            report.kept += 1
            continue
        _changed(
            report,
            title,
            before,
            after,
            record,
            [(by_id[int(ref[1:])], match) for ref, match in accepted],
            outcome,
            changes,
        )
    return matched_after


def _accepted(outcome: Outcome | None) -> list[tuple[str, dict[str, Any]]]:
    if outcome is None or outcome.answer is None:
        return []
    return [
        (m["candidate"], m) for m in outcome.answer.get("matches", []) if m.get("verdict") in ("matches", "partial")
    ]


def _needs_review(report: Report, title: str, before: Side, record: ActivityRecord, reason: str) -> None:
    item = _item(report, title, before, record, None)
    report.add(
        title,
        {
            "type": "loss",
            "title": f"Требует проверки: {_short(record.formulation, 70)}",
            "desc": reason,
            "from": [item],
            "to": [],
            "evidence": _evidence(
                "Проверка соответствия не завершена — это не установленная потеря.",
                "Проверка ИИ не выполнена",
                [_fact("До", record_sources(before, title, record, item))],
                "low",
            ),
        },
    )


def _loss(report: Report, title: str, before: Side, record: ActivityRecord, item: Candidates) -> None:
    item_id = _item(report, title, before, record, "loss")
    candidates = [
        {"label": _short(candidate.formulation, 80), "clause": "", "score": round(score, 3), "item": None}
        for candidate, score in item.checked
    ]
    report.add(
        title,
        {
            "type": "loss",
            "title": f"Возможная потеря: {_short(record.formulation, 70)}",
            "desc": f"Было закреплено за «{before.owner(record)}».",
            "from": [item_id],
            "to": [],
            "evidence": _evidence(
                "В предоставленных документах «после» закрепление функции не найдено — возможная потеря.",
                "Поиск по всем записям «после»: одинаковый текст и эмбеддинги, кандидаты проверены ИИ",
                [_fact(f"До: {before.owner(record)}", record_sources(before, title, record, item_id))],
                "medium",
                checked={
                    "scope": "Все записи деятельности документов «после»",
                    "threshold": 0.75,
                    "candidates": candidates,
                },
            ),
        },
    )


def _changed(
    report: Report,
    title: str,
    before: Side,
    after: Side,
    record: ActivityRecord,
    targets: list[tuple[ActivityRecord, dict[str, Any]]],
    outcome: Outcome | None,
    changes: list[str],
) -> None:
    moved = "executor" in changes
    kind = "moved" if moved else "transformed"
    item = _item(report, title, before, record, kind)
    to = [_item(report, title, after, target, kind) for target, _ in targets]
    steps = [_fact(f"До: {before.owner(record)}", record_sources(before, title, record, item))]
    steps += [_fact(f"После: {after.owner(t)}", record_sources(after, title, t, f"a_r{t.id}")) for t, _ in targets]
    explanation = "; ".join(m.get("explanation", "") for _, m in targets if m.get("explanation"))
    unmatched = outcome.answer.get("unmatched_part") if outcome and outcome.answer else None
    if explanation:
        steps.append(_inference(explanation))
    owners = ", ".join(dict.fromkeys(after.owner(t) for t, _ in targets))
    labels = ", ".join(CHANGE_LABELS[c] for c in changes) or "частичное покрытие"
    report.add(
        title,
        {
            "type": kind,
            "title": (
                f"Передано: {before.owner(record)} → {owners}"
                if moved
                else f"Изменено ({labels}): {_short(record.formulation, 60)}"
            ),
            "desc": f"Изменения: {labels}." + (f" Без продолжения: {unmatched}" if unmatched else ""),
            "from": [item],
            "to": to,
            "evidence": _evidence(
                f"Деятельность сохранилась; изменилось: {labels}.",
                "Кандидаты по эмбеддингам, проверка ИИ по цитатам",
                steps,
                "high" if outcome and outcome.answer and outcome.answer.get("coverage") == "full" else "medium",
            ),
        },
    )


def created_findings(report: Report, after: Side, matched_after: set[int]) -> None:
    """After records that no before record matched."""
    for record in after.records:
        if record.id in matched_after or record.record_type == "other":
            continue
        title = _block_for(after, record)
        item = _item(report, title, after, record, "created")
        report.add(
            title,
            {
                "type": "created",
                "title": f"Новая деятельность: {_short(record.formulation, 70)}",
                "desc": f"Закреплено за «{after.owner(record)}».",
                "from": [],
                "to": [item],
                "evidence": _evidence(
                    "В документах «после» описана деятельность без найденного соответствия в «до».",
                    "Ни одна запись «до» не была сопоставлена с этой записью",
                    [_fact("После", record_sources(after, title, record, item))],
                    "medium",
                    checked={"scope": "Все записи деятельности документов «до»", "threshold": 0.75, "candidates": []},
                ),
            },
        )


def duplication_findings(session: Session, report: Report, after: Side) -> None:
    """Verified 4.1 collisions of the after documents."""
    records = {record.id: record for record in after.records}
    for document in after.documents:
        pairs = session.scalars(
            select(CollisionPair).where(CollisionPair.document_id == document.id, CollisionPair.verdict == "collision"),
        ).all()
        for pair in pairs:
            sides = [records[rid] for rid in (pair.side_a_record_id, pair.side_b_record_id) if rid in records]
            to = [_item(report, DUPLICATION, after, record, None) for record in sides]
            steps = [_fact(after.owner(r), record_sources(after, DUPLICATION, r, f"a_r{r.id}")) for r in sides]
            if pair.explanation:
                steps.append(_inference(pair.explanation))
            report.add(
                DUPLICATION,
                {
                    "type": "duplication",
                    "title": "Возможное дублирование функций",
                    "desc": _short(pair.explanation or "", 200),
                    "from": [],
                    "to": to,
                    "evidence": _evidence(
                        "Функции разных объектов пересекаются (этап 4.1).",
                        "Эмбеддинги > 0,75 и проверка ИИ",
                        steps,
                        "medium",
                    ),
                },
            )


def job_result(job_id: str, report: Report, before: Side, after: Side) -> dict[str, Any]:
    """The ``JobResult`` payload."""
    counts: dict[str, int] = {"kept": report.kept}
    for finding in report.findings.values():
        counts[finding["type"]] = counts.get(finding["type"], 0) + 1
    blocks = [block for block in report.blocks.values() if block["changes"]]
    names = lambda side: ", ".join(d.title or d.file_name for d in side.documents)  # noqa: E731
    top = [
        f"{f['title']} ({fid})" for fid, f in report.findings.items() if f["type"] in ("loss", "moved", "duplication")
    ][:6]
    conclusion = (
        f"Сравнение «{names(before)}» (до) и «{names(after)}» (после). "
        + "; ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        + (". Главное: " + "; ".join(top) if top else "")
        + (f". Не проверено из-за ошибок: {report.errors}." if report.errors else ".")
        + " Выводы требуют проверки ответственным сотрудником."
    )
    return {
        "job_id": job_id,
        "summary": {"changed_blocks": [block["title"] for block in blocks], "counts": counts},
        "conclusion": conclusion,
        "blocks": blocks,
        "findings": report.findings,
    }
