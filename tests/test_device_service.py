import asyncio

import pytest

from app.services.device_service import CameraCaptureError, DeviceManager, DeviceProtocolError


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, **_kwargs):
        self.closed = True


async def start_request(manager, timeout=1):
    task = asyncio.create_task(manager.request_picture("argus-1", timeout))
    await asyncio.sleep(0)
    return task


@pytest.mark.asyncio
async def test_command_request_id_and_jpeg_round_trip():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    task = await start_request(manager)
    request_id = socket.sent[-1]["request_id"]
    assert socket.sent[-1] == {"type": "take_picture", "request_id": request_id}
    manager.start_image(connection, {
        "request_id": request_id, "content_type": "image/jpeg", "size": 4
    })
    manager.receive_image_bytes(connection, b"jpeg")
    manager.finish_image(connection, {"request_id": request_id})
    path = await task
    assert path.read_bytes() == b"jpeg"
    path.unlink()


@pytest.mark.asyncio
async def test_device_unavailable():
    with pytest.raises(CameraCaptureError, match="not connected"):
        await DeviceManager().request_picture("argus-1", 10)


@pytest.mark.asyncio
async def test_timeout_cleans_pending_request_and_partial_file():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    task = await start_request(manager, timeout=0.01)
    request_id = socket.sent[-1]["request_id"]
    manager.start_image(connection, {
        "request_id": request_id, "content_type": "image/jpeg"
    })
    path = connection.upload.path
    manager.receive_image_bytes(connection, b"partial")
    with pytest.raises(CameraCaptureError, match="timed out"):
        await task
    assert request_id not in manager.pending_captures
    assert connection.upload is None
    assert not path.exists()


@pytest.mark.asyncio
async def test_image_error_resolves_matching_future():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    task = await start_request(manager)
    request_id = socket.sent[-1]["request_id"]
    manager.image_error(connection, {"request_id": request_id, "message": "lens error"})
    with pytest.raises(CameraCaptureError, match="lens error"):
        await task


@pytest.mark.asyncio
async def test_incorrect_request_id_is_rejected():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    task = await start_request(manager)
    with pytest.raises(DeviceProtocolError, match="Unknown or expired"):
        manager.start_image(connection, {
            "request_id": "wrong", "content_type": "image/jpeg"
        })
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_disconnect_fails_capture_immediately():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    task = await start_request(manager, timeout=30)
    await manager.unregister(connection)
    with pytest.raises(CameraCaptureError, match="disconnected"):
        await task


@pytest.mark.asyncio
async def test_cancelled_request_cleans_partial_upload():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    task = await start_request(manager, timeout=30)
    request_id = socket.sent[-1]["request_id"]
    manager.start_image(connection, {
        "request_id": request_id, "content_type": "image/jpeg"
    })
    path = connection.upload.path
    manager.receive_image_bytes(connection, b"partial")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert request_id not in manager.pending_captures
    assert connection.upload is None
    assert not path.exists()


@pytest.mark.asyncio
async def test_two_request_ids_cannot_cross_associate():
    manager = DeviceManager()
    socket = FakeWebSocket()
    connection = await manager.register("argus-1", socket)
    first_task = await start_request(manager)
    second_task = await start_request(manager)
    first_id, second_id = [message["request_id"] for message in socket.sent[-2:]]
    paths = []
    for request_id, contents in [(second_id, b"second"), (first_id, b"first")]:
        manager.start_image(connection, {
            "request_id": request_id, "content_type": "image/jpeg"
        })
        manager.receive_image_bytes(connection, contents)
        manager.finish_image(connection, {"request_id": request_id})
        paths.append(await (second_task if request_id == second_id else first_task))
    assert not first_task.cancelled()
    assert {path.read_bytes() for path in paths} == {b"first", b"second"}
    for path in paths:
        path.unlink()


@pytest.mark.asyncio
async def test_reconnect_replaces_socket_and_fails_old_capture():
    manager = DeviceManager()
    old = FakeWebSocket()
    await manager.register("argus-1", old)
    task = await start_request(manager)
    new = FakeWebSocket()
    connection = await manager.register("argus-1", new)
    with pytest.raises(CameraCaptureError, match="reconnected"):
        await task
    assert old.closed
    assert manager.devices["argus-1"] is connection
