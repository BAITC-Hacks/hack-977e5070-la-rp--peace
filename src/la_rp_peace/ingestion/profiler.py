"""The language-model call that proposes a document's metadata and parsing profile."""

from typing import Protocol

import openai
from openai.types.chat import ChatCompletionMessageParam

from la_rp_peace.ingestion.prompt import Message


class ProfilerError(RuntimeError):
    """The model could not be reached or returned no answer."""


class Profiler(Protocol):
    """Anything that answers the profiling conversation with a JSON object as text."""

    def complete(self, messages: list[Message]) -> str:
        """Return the model's reply to the conversation."""
        ...


def _to_openai(message: Message) -> ChatCompletionMessageParam:
    if message.role == "system":
        return {"role": "system", "content": message.content}
    if message.role == "assistant":
        return {"role": "assistant", "content": message.content}
    return {"role": "user", "content": message.content}


class OpenAIProfiler:
    """Profiler backed by the OpenAI Chat Completions API in JSON mode."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout_seconds: float = 180) -> None:
        """Create the client.

        Args:
            api_key: OpenAI API key.
            model: Model name, e.g. from ``OPENAI_MODEL``.
            base_url: Alternative OpenAI-compatible endpoint, if any.
            timeout_seconds: Per-request timeout.
        """
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
        self._model = model

    def complete(self, messages: list[Message]) -> str:
        """Send the conversation and return the JSON text of the reply.

        Raises:
            ProfilerError: On API errors or an empty reply.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[_to_openai(message) for message in messages],
                response_format={"type": "json_object"},
            )
        except openai.OpenAIError as exc:
            raise ProfilerError(f"Ошибка обращения к модели: {exc}") from exc
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ProfilerError("Модель вернула пустой ответ")
        return content
