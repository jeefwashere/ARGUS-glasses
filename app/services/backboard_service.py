import os
from pathlib import Path
from typing import Optional

from backboard import BackboardClient

LLM_PROVIDER = "openai"
MODEL_NAME = "gpt-4o"

_client: Optional[BackboardClient] = None


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is missing")
    return value


def _get_client() -> BackboardClient:
    global _client

    if _client is None:
        _client = BackboardClient(api_key=_get_required_env("BACKBOARD_API_KEY"))

    return _client


async def call_backboard(
    question_text: str,
    image: str | Path | None = None,
    thread_id: str | None = None,
):
    if not question_text:
        raise ValueError("A question is required")

    client = _get_client()
    assistant_id = _get_required_env("BACKBOARD_ASSISTANT_ID")

    # Message with image
    if image:
        # First message with image needs a thread first
        if not thread_id:
            thread = await client.create_thread(assistant_id)
            thread_id = thread.thread_id

        response = await client.add_message(
            thread_id=thread_id,
            content=question_text,
            files=[image],
            llm_provider=LLM_PROVIDER,
            model_name=MODEL_NAME,
            stream=False,
        )

    # Text-only message
    else:
        response = await client.send_message(
            question_text,
            thread_id=thread_id,
            assistant_id=assistant_id,
            llm_provider=LLM_PROVIDER,
            model_name=MODEL_NAME,
            stream=False,
        )

    return {
        "content": response.content,
        "thread_id": response.thread_id,
        "assistant_id": response.assistant_id,
    }
