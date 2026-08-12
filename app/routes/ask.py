import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.backboard_service import call_backboard
from app.services.deepgram_service import DeepgramSession

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@router.websocket("/ask")
async def ask(websocket: WebSocket):
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
                {"type": "answer", "text": result["content"], "thread_id": thread_id}
            )
        except Exception:
            await send_error("Backboard failed to process the question")
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
        nonlocal thread_id
        nonlocal pending_image_path
        nonlocal receiving_image
        nonlocal upload_file
        nonlocal upload_path
        nonlocal image_expected

        if raw_text == "close":
            return False

        try:
            message = json.loads(raw_text)
        except json.JSONDecodeError:
            await send_error("Text messages must be valid JSON control messages")
            return True

        message_type = message.get("type")

        if message_type == "close":
            return False

        if message_type == "set_thread":
            new_thread_id = message.get("thread_id")
            if not new_thread_id:
                await send_error("set_thread requires thread_id")
                return True

            thread_id = new_thread_id
            await websocket.send_json({"type": "thread_set", "thread_id": thread_id})
            return True

        if message_type == "image_start":

            if receiving_image:
                await send_error("An image upload is already in progress")
                return True
            if pending_image_path:
                await send_error("An unused image is already waiting for a question")
                return True
            if submitting:
                await send_error(
                    "Cannot attach an image while a question is submitting"
                )
                return True

            content_type = message.get("content_type")
            suffix = ALLOWED_IMAGE_TYPES.get(content_type)
            if suffix is None:
                await send_error("Unsupported image type")
                return True

            upload_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            upload_path = Path(upload_file.name)

            receiving_image = True
            image_expected = True

            await websocket.send_json({"type": "image_started"})
            return True

        if message_type == "image_end":
            if not receiving_image or upload_file is None or upload_path is None:
                await send_error("No image upload is in progress")
                return True

            upload_file.close()
            pending_image_path = upload_path
            upload_file = None
            upload_path = None
            receiving_image = False
            await websocket.send_json({"type": "image_received"})
            await submit_pending_turn()
            return True

        await send_error("Unknown control message type")
        return True

    session = DeepgramSession(on_final_transcript=send_transcript)

    try:
        await session.connect()

        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            if text:
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
