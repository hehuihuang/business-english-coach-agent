from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI

from ..config import get_settings


@dataclass
class ModelResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict[str, Any]] | None = None


class AIProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], *, json_schema: dict | None = None) -> ModelResult: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockAIProvider:
    """Deterministic teaching provider used by tests and the zero-key demo."""

    async def complete(self, messages: list[dict[str, str]], *, json_schema: dict | None = None) -> ModelResult:
        learner_text = messages[-1]["content"] if messages else ""
        if json_schema:
            content = json.dumps({
                "intent": "writing" if "email" in learner_text.lower() else "coach",
                "plan": ["understand the business goal", "improve the English", "practice one reusable pattern"],
                "memory_candidates": [],
            })
        else:
            content = (
                "Here is a clearer business version:\n\n"
                f"“{learner_text.strip() or 'Could we align on the next steps by Friday?'}”\n\n"
                "编辑批注：先说目的，再给时间点，最后明确需要对方采取的行动。"
                " Try rephrasing it once in your own words."
            )
        return ModelResult(content=content, input_tokens=max(1, len(learner_text) // 4), output_tokens=len(content) // 4)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Stable pseudo-embeddings keep local tests meaningful without pretending
        # to have semantic quality. Production mode uses the configured provider.
        vectors = []
        dimensions = get_settings().embedding_dimensions
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [(digest[i % len(digest)] - 127.5) / 127.5 for i in range(dimensions)]
            norm = math.sqrt(sum(value * value for value in raw)) or 1
            vectors.append([value / norm for value in raw])
        return vectors


class OpenAICompatibleProvider:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)

    async def complete(self, messages: list[dict[str, str]], *, json_schema: dict | None = None) -> ModelResult:
        kwargs: dict[str, Any] = {"model": self.settings.ai_model, "messages": messages}
        if json_schema:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        response = await self.client.chat.completions.create(**kwargs)
        usage = response.usage
        return ModelResult(
            content=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            tool_calls=[call.model_dump() for call in response.choices[0].message.tool_calls or []],
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(model=self.settings.embedding_model, input=texts)
        return [item.embedding for item in response.data]


class SpeechProvider:
    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.ai_api_key, base_url=self.settings.ai_base_url)

    async def transcribe(self, audio: bytes, filename: str) -> str:
        if self.settings.speech_provider == "mock":
            return "Could we align on the next steps before Friday?"
        payload = io.BytesIO(audio)
        payload.name = filename
        response = await self.client.audio.transcriptions.create(model=self.settings.stt_model, file=payload)
        return response.text

    async def synthesize(self, text: str) -> bytes:
        if self.settings.speech_provider == "mock":
            return b"MOCK_AUDIO:" + text.encode()
        response = await self.client.audio.speech.create(
            model=self.settings.tts_model, voice=self.settings.tts_voice, input=text
        )
        return response.read()


def get_ai_provider() -> AIProvider:
    return MockAIProvider() if get_settings().ai_provider == "mock" else OpenAICompatibleProvider()
