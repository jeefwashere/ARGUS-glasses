import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.backboard_service import call_backboard
from app.services.deepgram_service import DeepgramSession
from app.services.elevenlabs_service import elevenlabs_tts

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@router.websocket("/ask")
async def ask(websocket: WebSocket):

    # Adding numbers to comments to indicate the flow order of architecture
    # 1. Websocket accepts or waits for connection
    await websocket.accept()

    thread_id: str | None = None
    pending_transcript: str | None = None
    pending_image_path: Path | None = None
    upload_file = None
    upload_path: Path | None = None
    receiving_image = False
    image_expected = False
    submitting = False

    async def send_error(message: str) -> None:
        await websocket.send_json({"type": "error", "message": message})

    def delete_path(path: Path | None) -> None:
        if path:
            path.unlink(missing_ok=True)

    async def submit_pending_turn() -> None:
        """Receives final transcript from Deepgram and image if present and gives it to Backboard"""

        nonlocal thread_id
        nonlocal pending_transcript
        nonlocal pending_image_path
        nonlocal submitting
        nonlocal image_expected

        if not pending_transcript or submitting:
            return

        if image_expected and pending_image_path is None:
            return

        question_text = pending_transcript
        image_path = pending_image_path

        pending_transcript = None
        pending_image_path = None
        image_expected = False
        submitting = True

        try:
            result = await call_backboard(
                question_text=question_text,
                image=image_path,
                thread_id=thread_id,
            )
            thread_id = result["thread_id"]

            await websocket.send_json(
                {
                    "type": "answer",
                    "text": result["content"],
                    "thread_id": thread_id,
                }
            )

            try:
                audio_bytes = await elevenlabs_tts(result["content"])

                await websocket.send_json(
                    {
                        "type": "audio_start",
                        "audio_format": "pcm_16000",
                    }
                )

                await websocket.send_bytes(audio_bytes)

                await websocket.send_json(
                    {
                        "type": "audio_end",
                    }
                )
            except Exception as ex:
                print(f"ElevenLabs TTS failed: {ex}")

                await websocket.send_json(
                    {"type": "audio_error", "message": "Speech generation failed."}
                )

        except Exception as ex:

            print(f"Turn processing failed: {ex}")
            await send_error("Failed to process the question")

        finally:
            delete_path(image_path)
            submitting = False
            await submit_pending_turn()

    async def send_transcript(text: str) -> None:
        nonlocal pending_transcript

        pending_transcript = text
        await websocket.send_json({"type": "transcript", "text": text})
        await submit_pending_turn()

    async def handle_control_message(raw_text: str) -> bool:
        """Handles text control messages such as stop, continue, image_end, image_start, etc.

        Args:
            raw_text (str): Control message

        Returns:
            bool: True being to keep the websocket loop running and false being to stop or close the websocket
        """
        nonlocal thread_id
        nonlocal pending_image_path
        nonlocal receiving_image
        nonlocal upload_file
        nonlocal upload_path
        nonlocal image_expected

        # If control message is close then return false to stop the websocket loop
        if raw_text == "close":
            return False

        try:
            # Deserialize the raw string into python objects in a dictionary
            message = json.loads(raw_text)

        # If text fails to convert to dictionary, keep the websocket open
        except json.JSONDecodeError:
            await send_error("Text messages must be valid JSON control messages")
            return True

        # Gets the value of the "type" field
        message_type = message.get("type")

        # Typed question from Framer
        if message_type == "question":
            question = (message.get("text") or "").strip()

            if not question:
                await send_error("question requires text")
                return True

            await send_transcript(question)
            return True

        # If the value is close then stop or close the websocket
        if message_type == "close":
            return False

        # Control block for restoring an existing Backboard thread
        if message_type == "set_thread":

            # Gets previously stored thread ID from the board
            new_thread_id = message.get("thread_id")
            if not new_thread_id:
                await send_error("set_thread requires thread_id")
                return True

            # Sets the current thread ID used by the backend
            thread_id = new_thread_id

            # Confirms to the board that the backend accepted the thread ID
            await websocket.send_json({"type": "thread_set", "thread_id": thread_id})
            return True

        # If the message contains an image
        if message_type == "image_start":

            # If an image is currently being received
            if receiving_image:
                await send_error("An image upload is already in progress")
                return True

            # If an image is already uploaded
            if pending_image_path:
                await send_error("An unused image is already waiting for a question")
                return True

            # If a question is being processed
            if submitting:
                await send_error(
                    "Cannot attach an image while a question is submitting"
                )
                return True

            # Gets image mime type
            content_type = message.get("content_type")
            suffix = ALLOWED_IMAGE_TYPES.get(content_type)
            if suffix is None:
                await send_error("Unsupported image type")
                return True

            # Creates an empty temp file that the image can write into later
            upload_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

            # Sets the path of the image as the path of the empty temp file
            upload_path = Path(upload_file.name)

            # Sets the flag to image is uploading
            receiving_image = True

            # An image is now included in the question
            image_expected = True

            # Confirmation sent to board that image is valid
            await websocket.send_json({"type": "image_started"})
            return True

        # If image bytes are done being received
        if message_type == "image_end":

            # Triggers if the image processing of earlier bytes encounters an error
            if not receiving_image or upload_file is None or upload_path is None:
                await send_error("No image upload is in progress")
                return True

            # Clears temp file
            upload_file.close()

            # Clears path
            pending_image_path = upload_path

            # Clears and resets variables and flags
            upload_file = None
            upload_path = None
            receiving_image = False
            await websocket.send_json({"type": "image_received"})
            await submit_pending_turn()
            return True

        await send_error("Unknown control message type")
        return True

    # 2. A Deepgram Session is instantiated
    # On_final_transcript is assigned an event callback where the send_transcript function triggers upon callback being called
    session = DeepgramSession(on_final_transcript=send_transcript)

    try:
        # 3. Connects to Deepgram
        await session.connect()

        # Continuously streaming the message, all these comments are handwritten btw
        while True:
            # Receives the message in the websocket
            message = await websocket.receive()

            # If disconnect message, stop listening
            if message.get("type") == "websocket.disconnect":
                break

            # Gets the content of "text" field
            text = message.get("text")
            if text:
                # Getting flag for websocket listening loop
                should_continue = await handle_control_message(text)
                if not should_continue:
                    break
                continue

            data = message.get("bytes")

            if data is None:
                continue

            if receiving_image:
                upload_file.write(data)
            else:
                await session.send_audio(data)

    except WebSocketDisconnect:
        print("Client disconnected from /ask")

    except Exception as exc:
        print(f"/ask failed: {exc}")

        try:
            await send_error("The ask WebSocket failed")
        except Exception:
            pass

    finally:
        await session.close()

        if upload_file is not None:
            upload_file.close()

        delete_path(upload_path)
        delete_path(pending_image_path)
