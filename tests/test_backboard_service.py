import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import backboard_service


class FakeBackboardClient:
    def __init__(self):
        self.create_thread_calls = []
        self.add_message_calls = []
        self.send_message_calls = []
        self.send_message_content = "text answer"

    async def create_thread(self, assistant_id):
        self.create_thread_calls.append(assistant_id)
        return SimpleNamespace(thread_id="created-thread")

    async def add_message(self, **kwargs):
        self.add_message_calls.append(kwargs)
        return SimpleNamespace(
            content="image answer",
            thread_id=kwargs["thread_id"],
            assistant_id="assistant-id",
        )

    async def send_message(self, content, **kwargs):
        self.send_message_calls.append({"content": content, **kwargs})
        return SimpleNamespace(
            content=self.send_message_content,
            thread_id=kwargs.get("thread_id") or "created-by-send-message",
            assistant_id=kwargs["assistant_id"],
        )


@pytest.fixture
def fake_backboard(monkeypatch):
    client = FakeBackboardClient()
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-id")
    monkeypatch.setattr(backboard_service, "_client", client)
    return client


def test_call_backboard_text_only_without_thread_uses_send_message(fake_backboard):
    result = asyncio.run(backboard_service.call_backboard("hello"))

    assert result["thread_id"] == "created-by-send-message"
    assert fake_backboard.create_thread_calls == []
    assert fake_backboard.send_message_calls == [
        {
            "content": "hello",
            "thread_id": None,
            "assistant_id": "assistant-id",
            "llm_provider": "openai",
            "model_name": "gpt-4o",
            "stream": False,
        }
    ]


def test_call_backboard_text_only_with_existing_thread(fake_backboard):
    result = asyncio.run(
        backboard_service.call_backboard("hello again", thread_id="existing-thread")
    )

    assert result["thread_id"] == "existing-thread"
    assert fake_backboard.create_thread_calls == []
    assert fake_backboard.send_message_calls[0]["thread_id"] == "existing-thread"


def test_call_backboard_image_without_thread_creates_thread(fake_backboard, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"image")

    result = asyncio.run(backboard_service.call_backboard("look", image=image))

    assert result["thread_id"] == "created-thread"
    assert fake_backboard.create_thread_calls == ["assistant-id"]
    assert fake_backboard.add_message_calls[0]["thread_id"] == "created-thread"
    assert fake_backboard.add_message_calls[0]["files"] == [image]


def test_call_backboard_image_with_existing_thread(fake_backboard, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"image")

    result = asyncio.run(
        backboard_service.call_backboard("look again", image=image, thread_id="thread-1")
    )

    assert result["thread_id"] == "thread-1"
    assert fake_backboard.create_thread_calls == []
    assert fake_backboard.add_message_calls[0]["thread_id"] == "thread-1"
    assert fake_backboard.add_message_calls[0]["files"] == [image]


def test_call_backboard_missing_question_raises(fake_backboard):
    with pytest.raises(ValueError, match="A question is required"):
        asyncio.run(backboard_service.call_backboard(""))


def test_call_backboard_missing_environment_raises(monkeypatch):
    monkeypatch.delenv("BACKBOARD_API_KEY", raising=False)
    monkeypatch.delenv("BACKBOARD_ASSISTANT_ID", raising=False)
    monkeypatch.setattr(backboard_service, "_client", None)

    with pytest.raises(ValueError, match="BACKBOARD_API_KEY is missing"):
        asyncio.run(backboard_service.call_backboard("hello"))


def test_decide_image_requirement_uses_structured_json_output(fake_backboard):
    fake_backboard.send_message_content = (
        '{"needs_image": false, "response": "Paris is the capital of France."}'
    )

    decision = asyncio.run(
        backboard_service.decide_image_requirement("What is the capital of France?")
    )

    assert decision.needs_image is False
    assert decision.response == "Paris is the capital of France."
    call = fake_backboard.send_message_calls[0]
    assert call["json_output"] is True
    assert call["system_prompt"] == backboard_service.ROUTING_SYSTEM_PROMPT


def test_decide_image_requirement_can_request_an_image(fake_backboard):
    fake_backboard.send_message_content = '{"needs_image": true, "response": null}'

    decision = asyncio.run(
        backboard_service.decide_image_requirement("What am I looking at?")
    )

    assert decision.needs_image is True
    assert decision.response is None
    assert decision.thread_id == "created-by-send-message"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"needs_image": "yes", "response": null}',
        '{"needs_image": true, "response": "premature answer"}',
        '{"needs_image": false, "response": null}',
    ],
)
def test_decide_image_requirement_rejects_invalid_output(fake_backboard, content):
    fake_backboard.send_message_content = content

    with pytest.raises(ValueError):
        asyncio.run(backboard_service.decide_image_requirement("question"))
