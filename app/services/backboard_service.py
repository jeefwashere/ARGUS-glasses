import os
from backboard import BackboardClient

# API Key for backboard.io
BACKBOARD_API_KEY = os.getenv("BACKBOARD_API_KEY")

if not BACKBOARD_API_KEY:
    raise ValueError("Backboard API Key is missing")

ASSISTANT_ID = os.getenv("BACKBOARD_ASSISTANT_ID")

if not ASSISTANT_ID:
    raise ValueError("Backboard Assistant ID is missing")

# Client variable for prompting backboard chosen llm
client = BackboardClient(api_key=BACKBOARD_API_KEY)

LLM_PROVIDER = "openai"
MODEL_NAME = "gpt-4o"


async def call_backboard(question_text, image=None, thread_id=None):
    if not question_text:
        raise ValueError("A question is required")

    if image:
        if not thread_id:
            thread = await client.create_thread(ASSISTANT_ID)
            thread_id = thread.thread_id

        response = await client.add_message(
            thread_id=thread_id,
            content=question_text,
            files=[image],
            llm_provider=LLM_PROVIDER,
            model_name=MODEL_NAME,
            stream=False,
        )

    else:
        response = await client.send_message(
            question_text,
            thread_id=thread_id,
            llm_provider=LLM_PROVIDER,
            model_name=MODEL_NAME,
            stream=False,
        )

    return {
        "content": response.content,
        "thread_id": response.thread_id,
        "assistant_id": response.assistant_id,
    }
