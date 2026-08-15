import asyncio
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from fastapi import WebSocket

logger = logging.getLogger(__name__)

DEFAULT_DEVICE_ID = "argus-1"
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class CameraCaptureError(RuntimeError):
    def __init__(self, message: str, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


class DeviceProtocolError(RuntimeError):
    def __init__(self, message: str, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


@dataclass(eq=False)
class ImageUpload:
    request_id: str
    content_type: str
    path: Path
    file: BinaryIO
    expected_size: int | None
    bytes_received: int = 0


@dataclass(eq=False)
class DeviceConnection:
    device_id: str
    websocket: WebSocket
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    upload: ImageUpload | None = None


@dataclass(eq=False)
class PendingCapture:
    request_id: str
    device_id: str
    connection: DeviceConnection
    future: asyncio.Future[Path]


def configured_device_id() -> str:
    return os.getenv("ARGUS_DEVICE_ID", DEFAULT_DEVICE_ID).strip() or DEFAULT_DEVICE_ID


class DeviceManager:
    def __init__(self, max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES):
        self.max_image_bytes = max_image_bytes
        self.devices: dict[str, DeviceConnection] = {}
        self.pending_captures: dict[str, PendingCapture] = {}

    async def register(self, device_id: str, websocket: WebSocket) -> DeviceConnection:
        connection = DeviceConnection(device_id=device_id, websocket=websocket)
        stale = self.devices.get(device_id)

        if stale is not None:
            self._fail_connection_captures(
                stale, "Camera device reconnected during capture"
            )
            self._discard_upload(stale)

        self.devices[device_id] = connection

        if stale is not None:
            try:
                await stale.websocket.close(code=1012, reason="Device reconnected")
            except Exception:
                logger.debug("Could not close stale device socket", exc_info=True)

        logger.info("[DEVICE] %s connected", device_id)
        return connection

    async def unregister(self, connection: DeviceConnection) -> None:
        if self.devices.get(connection.device_id) is connection:
            self.devices.pop(connection.device_id, None)

        self._fail_connection_captures(connection, "Camera device disconnected")
        self._discard_upload(connection)
        logger.info("[DEVICE] %s disconnected", connection.device_id)

    async def send_json(self, connection: DeviceConnection, payload: dict) -> None:
        async with connection.send_lock:
            await connection.websocket.send_json(payload)

    async def request_picture(self, device_id: str, timeout: float) -> Path:
        connection = self.devices.get(device_id)
        if connection is None:
            logger.warning("[CAMERA] Cannot request image: %s is offline", device_id)
            raise CameraCaptureError("Camera device is not connected")

        request_id = uuid.uuid4().hex
        future: asyncio.Future[Path] = asyncio.get_running_loop().create_future()
        pending = PendingCapture(request_id, device_id, connection, future)
        self.pending_captures[request_id] = pending
        logger.info(
            "[CAMERA] Creating request request_id=%s device=%s",
            request_id,
            device_id,
        )

        try:
            logger.info("[CAMERA] Sending take_picture request_id=%s", request_id)
            await self.send_json(
                connection, {"type": "take_picture", "request_id": request_id}
            )
        except Exception as exc:
            await self.unregister(connection)
            if future.done() and not future.cancelled():
                future.exception()
            raise CameraCaptureError(
                "Camera device disconnected", request_id
            ) from exc

        try:
            image_path = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            logger.info("[CAMERA] Capture completed request_id=%s", request_id)
            return image_path
        except TimeoutError as exc:
            logger.warning("[CAMERA] Timed out request_id=%s", request_id)
            if not future.done():
                future.cancel()
            self._discard_upload(connection, request_id)
            raise CameraCaptureError("Camera image timed out", request_id) from exc
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                try:
                    future.result().unlink(missing_ok=True)
                except CameraCaptureError:
                    pass
            else:
                future.cancel()
            self._discard_upload(connection, request_id)
            raise
        finally:
            if self.pending_captures.get(request_id) is pending:
                self.pending_captures.pop(request_id, None)
            if future.cancelled():
                self._discard_upload(connection, request_id)

    def start_image(self, connection: DeviceConnection, message: dict) -> dict:
        request_id = self._request_id(message)
        pending = self._owned_pending(connection, request_id)
        if connection.upload is not None:
            raise DeviceProtocolError(
                "An image upload is already in progress", request_id
            )

        content_type = message.get("content_type")
        suffix = ALLOWED_IMAGE_TYPES.get(content_type)
        if suffix is None:
            raise DeviceProtocolError("Unsupported image type", request_id)

        expected_size = message.get("size")
        if expected_size is not None:
            if (
                not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size < 0
                or expected_size > self.max_image_bytes
            ):
                raise DeviceProtocolError("Invalid image size", request_id)

        upload_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        connection.upload = ImageUpload(
            request_id=pending.request_id,
            content_type=content_type,
            path=Path(upload_file.name),
            file=upload_file,
            expected_size=expected_size,
        )
        logger.info(
            "[DEVICE] image_start request_id=%s type=%s size=%s",
            request_id,
            content_type,
            expected_size,
        )
        return {"type": "image_started", "request_id": request_id}

    def receive_image_bytes(self, connection: DeviceConnection, data: bytes) -> None:
        upload = connection.upload
        if upload is None:
            raise DeviceProtocolError("Binary data requires an active image upload")

        new_size = upload.bytes_received + len(data)
        if new_size > self.max_image_bytes:
            request_id = upload.request_id
            self._fail_capture(request_id, "Camera image exceeds maximum size")
            self._discard_upload(connection, request_id)
            raise DeviceProtocolError("Camera image exceeds maximum size", request_id)

        upload.file.write(data)
        upload.bytes_received = new_size

    def finish_image(self, connection: DeviceConnection, message: dict) -> dict:
        request_id = self._request_id(message)
        upload = connection.upload
        if upload is None:
            raise DeviceProtocolError("No image upload is in progress", request_id)
        if upload.request_id != request_id:
            raise DeviceProtocolError(
                "image_end request_id does not match image_start", request_id
            )

        upload.file.close()
        connection.upload = None
        logger.info(
            "[DEVICE] received %s bytes request_id=%s",
            upload.bytes_received,
            request_id,
        )
        logger.info("[DEVICE] image_end request_id=%s", request_id)

        error: str | None = None
        if upload.bytes_received == 0:
            error = "Camera returned an empty image"
        elif (
            upload.expected_size is not None
            and upload.bytes_received != upload.expected_size
        ):
            error = "Camera image size does not match image_start"

        if error is not None:
            upload.path.unlink(missing_ok=True)
            self._fail_capture(request_id, error)
            raise DeviceProtocolError(error, request_id)

        pending = self._owned_pending(connection, request_id)
        if pending.future.done():
            upload.path.unlink(missing_ok=True)
            raise DeviceProtocolError("Image request is no longer pending", request_id)
        pending.future.set_result(upload.path)
        return {"type": "image_received", "request_id": request_id}

    def image_error(self, connection: DeviceConnection, message: dict) -> None:
        request_id = self._request_id(message)
        self._owned_pending(connection, request_id)
        detail = message.get("message")
        if not isinstance(detail, str) or not detail.strip():
            detail = "Camera capture failed"
        else:
            detail = detail.strip()
        self._discard_upload(connection, request_id)
        self._fail_capture(request_id, detail)

    def _request_id(self, message: dict) -> str:
        request_id = message.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise DeviceProtocolError("Camera message requires request_id")
        return request_id

    def _owned_pending(
        self, connection: DeviceConnection, request_id: str
    ) -> PendingCapture:
        pending = self.pending_captures.get(request_id)
        if pending is None or pending.connection is not connection:
            raise DeviceProtocolError("Unknown or expired image request", request_id)
        return pending

    def _fail_capture(self, request_id: str, message: str) -> None:
        pending = self.pending_captures.get(request_id)
        if pending is not None and not pending.future.done():
            pending.future.set_exception(CameraCaptureError(message, request_id))

    def _fail_connection_captures(
        self, connection: DeviceConnection, message: str
    ) -> None:
        for pending in tuple(self.pending_captures.values()):
            if pending.connection is connection and not pending.future.done():
                pending.future.set_exception(
                    CameraCaptureError(message, pending.request_id)
                )

    def _discard_upload(
        self, connection: DeviceConnection, request_id: str | None = None
    ) -> None:
        upload = connection.upload
        if upload is None or (
            request_id is not None and upload.request_id != request_id
        ):
            return
        if not upload.file.closed:
            upload.file.close()
        upload.path.unlink(missing_ok=True)
        connection.upload = None


device_manager = DeviceManager()
