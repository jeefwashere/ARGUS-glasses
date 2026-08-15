import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.device_service import DeviceProtocolError, device_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/device")
async def device_websocket(websocket: WebSocket):
    await websocket.accept()

    device_id = (websocket.query_params.get("device_id") or "").strip()
    expected_token = os.getenv("ARGUS_DEVICE_TOKEN")
    supplied_token = websocket.query_params.get("token")
    if not device_id:
        await websocket.send_json(
            {"type": "error", "message": "device_id query parameter is required"}
        )
        await websocket.close(code=1008)
        return
    if expected_token and supplied_token != expected_token:
        await websocket.send_json({"type": "error", "message": "Invalid device token"})
        await websocket.close(code=1008)
        return

    connection = await device_manager.register(device_id, websocket)
    await device_manager.send_json(
        connection, {"type": "device_connected", "device_id": device_id}
    )

    try:
        while True:
            frame = await websocket.receive()
            if frame.get("type") == "websocket.disconnect":
                break

            data = frame.get("bytes")
            if data is not None:
                try:
                    device_manager.receive_image_bytes(connection, data)
                except DeviceProtocolError as exc:
                    await device_manager.send_json(
                        connection,
                        {
                            "type": "error",
                            "message": str(exc),
                            **({"request_id": exc.request_id} if exc.request_id else {}),
                        },
                    )
                continue

            raw_text = frame.get("text")
            if raw_text is None:
                continue
            if raw_text == "close":
                break
            try:
                message = json.loads(raw_text)
                if not isinstance(message, dict):
                    raise DeviceProtocolError("Device messages must be JSON objects")
                message_type = message.get("type")
                if message_type == "image_start":
                    response = device_manager.start_image(connection, message)
                elif message_type == "image_end":
                    response = device_manager.finish_image(connection, message)
                elif message_type == "image_error":
                    device_manager.image_error(connection, message)
                    response = None
                elif message_type == "close":
                    break
                else:
                    raise DeviceProtocolError("Unknown device message type")
                if response is not None:
                    await device_manager.send_json(connection, response)
            except json.JSONDecodeError:
                await device_manager.send_json(
                    connection,
                    {"type": "error", "message": "Device messages must be valid JSON"},
                )
            except DeviceProtocolError as exc:
                payload = {"type": "error", "message": str(exc)}
                if exc.request_id:
                    payload["request_id"] = exc.request_id
                await device_manager.send_json(connection, payload)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("/device failed for %s: %s", device_id, exc)
    finally:
        await device_manager.unregister(connection)
