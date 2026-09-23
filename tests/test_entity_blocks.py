import json
from pathlib import Path

import pytest
from entities_support import parsed_document, session_factory
from sqlalchemy import select

from la_rp_peace.entities.blocks import Block, plan_blocks
from la_rp_peace.models import Document, DocumentNode
from la_rp_peace.navigation import describe


def _blocks(tmp_path: Path, max_chars: int) -> list[Block]:
    factory = session_factory(tmp_path)
    document_id = parsed_document(factory, 9)
    with factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        nodes = list(session.scalars(select(DocumentNode).where(DocumentNode.document_id == document_id)))
        return plan_blocks(nodes, describe(nodes, json.loads(document.source_map)), max_chars)


def _texts(block: Block) -> list[str]:
    return [line.text for line in block.lines]


def test_front_matter_and_sections_become_blocks(tmp_path: Path) -> None:
    blocks = _blocks(tmp_path, 12_000)

    front = _texts(blocks[0])
    structure = next(
        block for block in blocks if "3.4. БВА состоит из следующих структурных подразделений:" in _texts(block)
    )

    assert front[:2] == ["УТВЕРЖДЕНО", "Советом директоров"]
    assert not any(line.context for line in structure.lines)
    assert {"в. Аудитор.", "б. Департамент операционного аудита (ДОА)."} <= set(_texts(structure))
    assert not any("ОГЛАВЛЕНИЕ" in text for block in blocks for text in _texts(block))
    rendered = structure.render().splitlines()[0]
    assert rendered.startswith(
        f"[node {structure.root_id}] Разд. 3 «Структура и организация работы внутреннего аудита» | 3."
    )


@pytest.mark.parametrize("max_chars", [1_500, 3_000])
def test_split_sections_keep_intro_phrases_with_their_lists(tmp_path: Path, max_chars: int) -> None:
    blocks = _blocks(tmp_path, max_chars)

    for block in blocks:
        texts = _texts(block)
        if "в. Аудитор." in texts:
            assert any(text.startswith(("3.6. Директору ДИТААД", "3.7. Директору ДОА")) for text in texts)
        if len(block.lines) > 1 and block.lines[0].context:
            assert block.lines[0].text[0].isdigit()
    roots = [block.root_id for block in blocks]
    assert len(roots) == len(set(roots))
    assert all(
        len(block.render()) <= max_chars or len([line for line in block.lines if not line.context]) == 1
        for block in blocks
    )
