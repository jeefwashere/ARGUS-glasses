from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.deepgram import DeepgramSession

router = APIRouter()


@router.websocket("/ask")
async def ask(websocket: WebSocket):
    await websocket.accept()

    async def send_transcript(text: str) -> None:
        await websocket.send_json({"type": "transcript", "text": text})

    try:
        async with DeepgramSession(on_final_transcript=send_transcript) as session:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                # The client must send 16 kHz mono signed 16-bit PCM chunks.
                audio_chunk = message.get("bytes")
                if audio_chunk is not None:
                    await session.send_audio(audio_chunk)
                    continue

                # Optional convenience for browser clients that send a stop command.
                text = message.get("text")
                if text == "close":
                    break

    except WebSocketDisconnect:
        print("Client disconnected from /ask")
    except Exception as exc:
        print(f"/ask failed: {exc}")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
