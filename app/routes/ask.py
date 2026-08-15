import asyncio
import json
import logging
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.backboard_service import call_backboard, decide_image_requirement
from app.services.deepgram_service import DeepgramSession
from app.services.elevenlabs_service import elevenlabs_tts
from app.utils.audio import pcm16_mono_16k_to_stereo_44100, pcm16_to_wav
from app.utils.wake_word import WAKE_PHRASE, extract_wake_question

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

WAKE_WINDOW_SECONDS = 10
IMAGE_TIMEOUT_SECONDS = 15


class CameraCaptureError(RuntimeError):
    def __init__(self, message: str, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


@router.websocket("/ask")
async def ask(websocket: WebSocket):
    await websocket.accept()

    thread_id: str | None = None
    wake_armed_until = 0.0
    turn_lock = asyncio.Lock()
    send_lock = asyncio.Lock()
    turn_tasks: set[asyncio.Task] = set()

    # Each requested camera image resolves exactly one waiting conversation turn.
    pending_images: dict[str, asyncio.Future[Path]] = {}
    legacy_image_future: asyncio.Future[Path] | None = None
    upload_file = None
    upload_path: Path | None = None
    upload_request_id: str | None = None
    receiving_image = False

    async def send_json(message: dict) -> None:
        async with send_lock:
            await websocket.send_json(message)

    async def send_error(message: str, request_id: str | None = None) -> None:
        payload = {"type": "error", "message": message}
        if request_id:
            payload["request_id"] = request_id
        await send_json(payload)

    def delete_path(path: Path | None) -> None:
        if path:
            path.unlink(missing_ok=True)

    def discard_active_upload(expected_request_id: str | None) -> None:
        nonlocal receiving_image, upload_file, upload_path, upload_request_id

        if not receiving_image or upload_request_id != expected_request_id:
            return
        if upload_file is not None:
            upload_file.close()
        delete_path(upload_path)
        upload_file = None
        upload_path = None
        upload_request_id = None
        receiving_image = False

    async def request_picture(request_id: str) -> None:
        logger.info("Requesting camera image... request_id=%s", request_id)
        await send_json({"type": "take_picture", "request_id": request_id})

    async def wait_for_picture() -> Path:
        nonlocal receiving_image, upload_file, upload_path, upload_request_id

        request_id = uuid.uuid4().hex
        future: asyncio.Future[Path] = asyncio.get_running_loop().create_future()
        pending_images[request_id] = future
        await request_picture(request_id)

        try:
            return await asyncio.wait_for(future, timeout=IMAGE_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            logger.warning("Camera image timed out request_id=%s", request_id)
            discard_active_upload(request_id)
            raise CameraCaptureError("Camera image timed out", request_id) from exc
        finally:
            pending_images.pop(request_id, None)

    async def send_final_answer(answer: str, current_thread_id: str) -> None:
        await send_json(
            {"type": "answer", "text": answer, "thread_id": current_thread_id}
        )

        try:
            logger.info("Sending response to ElevenLabs...")
            pcm_audio = await elevenlabs_tts(answer)
            logger.info(
                "[AUDIO] ElevenLabs PCM received: %s bytes; source: "
                "16000 Hz mono 16-bit",
                len(pcm_audio),
            )
            logger.info(
                "[AUDIO] Converting for Bluetooth; target: 44100 Hz stereo 16-bit"
            )
            bluetooth_pcm = pcm16_mono_16k_to_stereo_44100(pcm_audio)
            logger.info("[AUDIO] Converted PCM: %s bytes", len(bluetooth_pcm))
            wav_audio = pcm16_to_wav(
                bluetooth_pcm,
                sample_rate=44100,
                channels=2,
            )
            logger.info("[AUDIO] Sending Bluetooth-ready WAV to ESP32")
            # Keep the audio envelope atomic so an unrelated control message
            # cannot appear between audio_start, the WAV bytes, and audio_end.
            async with send_lock:
                await websocket.send_json(
                    {
                        "type": "audio_start",
                        "audio_format": "wav_44100_stereo",
                        "sample_rate": 44100,
                        "channels": 2,
                        "bits_per_sample": 16,
                    }
                )
                await websocket.send_bytes(wav_audio)
                await websocket.send_json({"type": "audio_end"})
        except Exception as exc:
            logger.exception(
                "ElevenLabs TTS or Bluetooth audio conversion failed: %s", exc
            )
            await send_json(
                {"type": "audio_error", "message": "Speech generation failed."}
            )

    async def process_turn(question_text: str) -> None:
        nonlocal thread_id, legacy_image_future

        image_path: Path | None = None
        async with turn_lock:
            try:
                decision = await decide_image_requirement(
                    question_text=question_text,
                    thread_id=thread_id,
                )
                thread_id = decision.thread_id
                logger.info(
                    "Backboard decision: needs_image=%s", decision.needs_image
                )

                # Requestless image_start/image_end remains an explicit manual
                # attachment for clients using the original protocol.
                if legacy_image_future is not None:
                    manual_image = legacy_image_future
                    try:
                        image_path = await asyncio.wait_for(
                            manual_image, timeout=IMAGE_TIMEOUT_SECONDS
                        )
                    except TimeoutError as exc:
                        discard_active_upload(None)
                        raise CameraCaptureError("Camera image timed out") from exc
                    finally:
                        if legacy_image_future is manual_image:
                            legacy_image_future = None

                if decision.needs_image or image_path is not None:
                    if image_path is None:
                        image_path = await wait_for_picture()
                    logger.info("Sending question + image to Backboard...")
                    result = await call_backboard(
                        question_text=question_text,
                        image=image_path,
                        thread_id=thread_id,
                    )
                    thread_id = result["thread_id"]
                    answer = result["content"]
                else:
                    answer = decision.response

                logger.info("Backboard final response: %s", answer)
                await send_final_answer(answer, thread_id)
            except CameraCaptureError as exc:
                await send_error(str(exc), exc.request_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Turn processing failed: %s", exc)
                await send_error("Failed to process the question")
            finally:
                delete_path(image_path)

    def start_turn(question_text: str) -> None:
        task = asyncio.create_task(process_turn(question_text))
        turn_tasks.add(task)
        task.add_done_callback(turn_tasks.discard)

    async def send_transcript(text: str) -> None:
        logger.info("Transcript: %s", text)
        await send_json({"type": "transcript", "text": text})
        start_turn(text)

    async def handle_voice_transcript(text: str) -> None:
        nonlocal wake_armed_until

        spoken_text = text.strip()
        if not spoken_text:
            return

        wake_detected, question = extract_wake_question(spoken_text)
        if wake_detected:
            if question:
                wake_armed_until = 0.0
                await send_transcript(question)
                return

            wake_armed_until = time.monotonic() + WAKE_WINDOW_SECONDS
            await send_json(
                {
                    "type": "wake_detected",
                    "text": spoken_text,
                    "wake_phrase": WAKE_PHRASE,
                    "window_seconds": WAKE_WINDOW_SECONDS,
                }
            )
            return

        if time.monotonic() <= wake_armed_until:
            wake_armed_until = 0.0
            await send_transcript(spoken_text)
            return

        wake_armed_until = 0.0
        await send_json(
            {
                "type": "wake_ignored",
                "text": spoken_text,
                "wake_phrase": WAKE_PHRASE,
            }
        )

    async def handle_control_message(raw_text: str) -> bool:
        nonlocal thread_id, legacy_image_future
        nonlocal receiving_image, upload_file, upload_path, upload_request_id

        if raw_text == "close":
            return False

        try:
            message = json.loads(raw_text)
        except json.JSONDecodeError:
            await send_error("Text messages must be valid JSON control messages")
            return True

        message_type = message.get("type")

        if message_type == "question":
            question = (message.get("text") or "").strip()
            if not question:
                await send_error("question requires text")
                return True
            await send_transcript(question)
            return True

        if message_type == "close":
            return False

        if message_type == "set_thread":
            new_thread_id = message.get("thread_id")
            if not new_thread_id:
                await send_error("set_thread requires thread_id")
                return True
            if turn_lock.locked():
                await send_error("Cannot change thread while a question is processing")
                return True
            thread_id = new_thread_id
            await send_json({"type": "thread_set", "thread_id": thread_id})
            return True

        if message_type == "image_start":
            if receiving_image:
                await send_error("An image upload is already in progress")
                return True

            request_id = message.get("request_id")
            if request_id is not None:
                if request_id not in pending_images:
                    await send_error("Unknown or expired image request", request_id)
                    return True
            elif pending_images:
                await send_error("Camera image requires request_id")
                return True
            elif legacy_image_future is not None:
                await send_error("An unused image is already waiting for a question")
                return True

            content_type = message.get("content_type")
            suffix = ALLOWED_IMAGE_TYPES.get(content_type)
            if suffix is None:
                await send_error("Unsupported image type", request_id)
                return True

            upload_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            upload_path = Path(upload_file.name)
            upload_request_id = request_id
            receiving_image = True
            if request_id is None:
                legacy_image_future = asyncio.get_running_loop().create_future()

            response = {"type": "image_started"}
            if request_id:
                response["request_id"] = request_id
            await send_json(response)
            return True

        if message_type == "image_end":
            if not receiving_image or upload_file is None or upload_path is None:
                await send_error("No image upload is in progress")
                return True

            request_id = message.get("request_id")
            if request_id != upload_request_id:
                await send_error("image_end request_id does not match image_start")
                return True

            upload_file.close()
            completed_path = upload_path
            completed_request_id = upload_request_id
            size = completed_path.stat().st_size
            upload_file = None
            upload_path = None
            upload_request_id = None
            receiving_image = False

            response = {"type": "image_received"}
            if completed_request_id:
                response["request_id"] = completed_request_id
            await send_json(response)
            logger.info(
                "ESP32 image received request_id=%s size=%s bytes",
                completed_request_id or "legacy",
                size,
            )

            if completed_request_id:
                future = pending_images.get(completed_request_id)
                if future is not None and not future.done():
                    future.set_result(completed_path)
                else:
                    delete_path(completed_path)
            else:
                if legacy_image_future is not None and not legacy_image_future.done():
                    legacy_image_future.set_result(completed_path)
                else:
                    delete_path(completed_path)
            return True

        if message_type == "image_error":
            request_id = message.get("request_id")
            future = pending_images.get(request_id)
            if future is None or future.done():
                await send_error("Unknown or expired image request", request_id)
                return True
            detail = (message.get("message") or "Camera capture failed").strip()
            discard_active_upload(request_id)
            future.set_exception(CameraCaptureError(detail, request_id))
            return True

        await send_error("Unknown control message type")
        return True

    session = DeepgramSession(on_final_transcript=handle_voice_transcript)

    try:
        await session.connect()

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            if text:
                if not await handle_control_message(text):
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
        logger.info("Client disconnected from /ask")
    except Exception as exc:
        logger.exception("/ask failed: %s", exc)
        try:
            await send_error("The ask WebSocket failed")
        except Exception:
            pass
    finally:
        await session.close()

        for task in tuple(turn_tasks):
            task.cancel()
        if turn_tasks:
            await asyncio.gather(*turn_tasks, return_exceptions=True)

        if upload_file is not None:
            upload_file.close()
        delete_path(upload_path)
        if legacy_image_future is not None and legacy_image_future.done():
            try:
                delete_path(legacy_image_future.result())
            except (asyncio.CancelledError, Exception):
                pass
