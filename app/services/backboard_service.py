import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backboard import BackboardClient

LLM_PROVIDER = "openai"
MODEL_NAME = "gpt-4o"

_client: Optional[BackboardClient] = None

ROUTING_SYSTEM_PROMPT = """You route questions for smart glasses and answer them when vision is not needed.
Return one JSON object with exactly these fields:
- needs_image: boolean
- response: string when needs_image is false, otherwise null

Set needs_image to true only when answering depends on the user's current visual scene, such as
identifying an object, reading or translating visible text, describing what the user sees, or
determining a visible property such as color. Set it to false for general knowledge, arithmetic,
language questions, and anything answerable from the text alone. When needs_image is false,
response must be the complete user-facing answer. Do not include markdown fences or commentary."""


@dataclass(frozen=True)
class BackboardDecision:
    needs_image: bool
    response: str | None
    thread_id: str
    assistant_id: str


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


def _parse_decision(content: object) -> tuple[bool, str | None]:
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("Backboard returned an invalid routing decision") from exc
    elif isinstance(content, dict):
        payload = content
    else:
        raise ValueError("Backboard returned an invalid routing decision")

    if not isinstance(payload, dict):
        raise ValueError("Backboard returned an invalid routing decision")
    if set(payload) != {"needs_image", "response"}:
        raise ValueError("Backboard routing decision has unexpected fields")

    needs_image = payload.get("needs_image")
    response = payload.get("response")
    if not isinstance(needs_image, bool):
        raise ValueError("Backboard routing decision is missing needs_image")
    if needs_image:
        if response is not None:
            raise ValueError("Image routing responses must not contain a final answer")
    elif not isinstance(response, str) or not response.strip():
        raise ValueError("Text routing responses must contain a final answer")

    return needs_image, response


async def decide_image_requirement(
    question_text: str,
    thread_id: str | None = None,
) -> BackboardDecision:
    """Ask Backboard to either answer the question or request a camera image."""
    if not question_text:
        raise ValueError("A question is required")

    client = _get_client()
    assistant_id = _get_required_env("BACKBOARD_ASSISTANT_ID")
    result = await client.send_message(
        question_text,
        thread_id=thread_id,
        assistant_id=assistant_id,
        system_prompt=ROUTING_SYSTEM_PROMPT,
        llm_provider=LLM_PROVIDER,
        model_name=MODEL_NAME,
        stream=False,
        json_output=True,
    )
    needs_image, response = _parse_decision(result.content)
    return BackboardDecision(
        needs_image=needs_image,
        response=response,
        thread_id=str(result.thread_id),
        assistant_id=str(result.assistant_id),
    )


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
