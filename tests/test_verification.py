"""Runtime parallelism configuration for shared analysis verification."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from la_rp_peace.verification import ask_in_batches


@pytest.mark.parametrize(("override", "expected"), [(None, 50), (3, 3)])
def test_verification_parallelism_uses_settings_unless_overridden(override: int | None, expected: int) -> None:
    """All callers without an explicit limit use the configured worker count."""
    with (
        patch("la_rp_peace.verification.get_settings", return_value=SimpleNamespace(analysis_parallel=50)),
        patch("la_rp_peace.verification.ThreadPoolExecutor", wraps=ThreadPoolExecutor) as executor,
    ):
        result = ask_in_batches(Mock(), "", [], lambda _question, _answer: [], retries=0, parallel=override)
    assert result == {}
    executor.assert_called_once_with(max_workers=expected, thread_name_prefix="verification")
