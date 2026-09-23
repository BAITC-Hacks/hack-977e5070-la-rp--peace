"""Real profiling calls. Run with ``uv run pytest -m live`` once OPENAI_API_KEY and OPENAI_MODEL are set."""

import pytest
from conftest import edition_path

from la_rp_peace.config import Settings
from la_rp_peace.enums import NodeType, ParseStatus
from la_rp_peace.ingestion.analysis import analyse
from la_rp_peace.ingestion.extract import detect_format, extract
from la_rp_peace.ingestion.profiler import OpenAIProfiler

pytestmark = pytest.mark.live


@pytest.fixture
def profiler() -> OpenAIProfiler:
    settings = Settings()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value() or not settings.openai_model:
        pytest.skip("OPENAI_API_KEY and OPENAI_MODEL are not set")
    return OpenAIProfiler(
        settings.openai_api_key.get_secret_value(),
        settings.openai_model,
        base_url=settings.openai_base_url or None,
        reasoning_effort=settings.openai_reasoning_effort,
    )


@pytest.mark.parametrize("suffix", [".docx", ".pdf"])
def test_model_profiles_edition_9(profiler: OpenAIProfiler, suffix: str) -> None:
    path = edition_path(9, suffix)
    extraction = extract(detect_format(path.name, path.read_bytes()), path.read_bytes())

    result = analyse(extraction, profiler, max_chars=150_000, retries=2)

    sections = [node.marker for node in result.nodes if node.node_type is NodeType.SECTION]
    assert result.status is ParseStatus.VALIDATED, [issue.message for issue in result.issues]
    assert sections == [str(number) for number in range(1, 15)]
    assert result.metadata is not None
    assert result.metadata.card["approved_on"] == "2022-12-23"
    assert result.metadata.card["approval_number"] == "7"
