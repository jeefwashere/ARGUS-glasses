# create_assistant.py

import os
import asyncio
from backboard import BackboardClient
from dotenv import load_dotenv

load_dotenv()

BACKBOARD_API_KEY = os.getenv("BACKBOARD_API_KEY")

if not BACKBOARD_API_KEY:
    raise ValueError("BACKBOARD_API_KEY is missing")

client = BackboardClient(api_key=BACKBOARD_API_KEY)


async def main():
    assistant = await client.create_assistant(
        name="Study Assistant", system_prompt="You are a helpful study assistant."
    )

    print("Assistant ID:", assistant.assistant_id)


asyncio.run(main())
