import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.backboard_service import call_backboard, decide_image_requirement
from app.services.deepgram_service import DeepgramSession
from app.services.device_service import (
    CameraCaptureError,
    configured_device_id,
    device_manager,
)
from app.services.elevenlabs_service import elevenlabs_tts
from app.utils.audio import pcm16_mono_16k_to_stereo_44100, pcm16_to_wav
from app.utils.wake_word import WAKE_PHRASE, extract_wake_question

router = APIRouter()
logger = logging.getLogger(__name__)

WAKE_WINDOW_SECONDS = 10
IMAGE_TIMEOUT_SECONDS = 15
AUDIO_OUTPUT_BROWSER = "browser"
AUDIO_OUTPUT_ESP32_BLUETOOTH = "esp32_bluetooth"
SUPPORTED_AUDIO_OUTPUT_MODES = {
    AUDIO_OUTPUT_BROWSER,
    AUDIO_OUTPUT_ESP32_BLUETOOTH,
}


def configured_audio_output_mode() -> str:
    mode = os.getenv("AUDIO_OUTPUT_MODE", AUDIO_OUTPUT_BROWSER).strip().lower()
    if mode not in SUPPORTED_AUDIO_OUTPUT_MODES:
        logger.warning(
            "Unsupported AUDIO_OUTPUT_MODE=%r; defaulting to browser", mode
        )
        return AUDIO_OUTPUT_BROWSER
    return mode


@router.websocket("/ask")
async def ask(websocket: WebSocket):
    await websocket.accept()

    thread_id: str | None = None
    wake_armed_until = 0.0
    turn_lock = asyncio.Lock()
    send_lock = asyncio.Lock()
    turn_tasks: set[asyncio.Task] = set()

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

            audio_output_mode = configured_audio_output_mode()
            if audio_output_mode == AUDIO_OUTPUT_BROWSER:
                wav_audio = pcm16_to_wav(pcm_audio)
                await send_json(
                    {
                        "type": "audio",
                        "audio_base64": base64.b64encode(wav_audio).decode("ascii"),
                        "audio_mime_type": "audio/wav",
                        "audio_format": "wav_16000_mono",
                        "sample_rate": 16000,
                        "channels": 1,
                        "bits_per_sample": 16,
                    }
                )
                return

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
            logger.exception("ElevenLabs TTS or audio routing failed: %s", exc)
            await send_json(
                {"type": "audio_error", "message": "Speech generation failed."}
            )

    async def process_turn(question_text: str) -> None:
        nonlocal thread_id

        image_path: Path | None = None
        async with turn_lock:
            try:
                decision = await decide_image_requirement(
                    question_text=question_text,
                    thread_id=thread_id,
                )
                thread_id = decision.thread_id
                logger.info(
                    "[BACKBOARD] needs_image=%s", str(decision.needs_image).lower()
                )

                if decision.needs_image:
                    image_path = await device_manager.request_picture(
                        device_id=configured_device_id(),
                        timeout=IMAGE_TIMEOUT_SECONDS,
                    )
                    logger.info(
                        "[BACKBOARD] Sending original question + captured image"
                    )
                    result = await call_backboard(
                        question_text=question_text,
                        image=image_path,
                        thread_id=thread_id,
                    )
                    thread_id = result["thread_id"]
                    answer = result["content"]
                    logger.info("[BACKBOARD] Final response received")
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
        nonlocal thread_id

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
