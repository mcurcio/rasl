"""DDPClient: the packets it puts on the wire, read back from a loopback socket."""

from __future__ import annotations

import socket
import struct
from collections.abc import Iterator

import numpy as np
import pytest

from rasl.devices.ddp.client import DDP_MAX_DATALEN, DDPClient

_VERSION_1 = 0x40
_PUSH = 0x01


@pytest.fixture
def receiver() -> Iterator[socket.socket]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    yield sock
    sock.close()


@pytest.fixture
def client(receiver: socket.socket) -> Iterator[DDPClient]:
    made = DDPClient("127.0.0.1", port=receiver.getsockname()[1])
    made.connect(blocking=False)
    yield made
    made.close()


def _packets(receiver: socket.socket, count: int) -> list[tuple[int, int, int, int, int, bytes]]:
    """``count`` packets as (flags, sequence, data type, destination, offset, data)."""
    out = []
    for _ in range(count):
        raw = receiver.recv(2048)
        flags, sequence, data_type, destination, offset, length = struct.unpack("!BBBBLH", raw[:10])
        assert length == len(raw) - 10
        out.append((flags, sequence, data_type, destination, offset, raw[10:]))
    return out


def test_floats_are_sent_as_bytes_in_one_pushed_packet(client: DDPClient, receiver: socket.socket) -> None:
    client.send(np.array([[0.0, 0.5, 1.0], [2.0, -1.0, 0.25]], dtype=np.float32))
    [(flags, sequence, data_type, destination, offset, data)] = _packets(receiver, 1)
    assert flags == _VERSION_1 | _PUSH
    assert (sequence, data_type, destination, offset) == (1, 0x00, 0x01, 0)
    assert list(data) == [0, 127, 255, 255, 0, 63]  # clipped to 0..1, then scaled


def test_a_long_frame_is_split_at_1440_bytes_and_only_the_last_packet_pushes(
    client: DDPClient, receiver: socket.socket
) -> None:
    pixels = (np.arange(3000) % 256).astype(np.uint8)
    client.send(pixels)
    packets = _packets(receiver, 3)
    assert [p[4] for p in packets] == [0, DDP_MAX_DATALEN, 2 * DDP_MAX_DATALEN]
    assert [len(p[5]) for p in packets] == [1440, 1440, 120]
    assert [p[0] for p in packets] == [_VERSION_1, _VERSION_1, _VERSION_1 | _PUSH]
    assert [p[1] for p in packets] == [1, 2, 3]
    assert b"".join(p[5] for p in packets) == pixels.tobytes()


def test_the_sequence_number_runs_1_to_15_and_wraps(client: DDPClient, receiver: socket.socket) -> None:
    for _ in range(17):
        client.send(np.zeros(3, dtype=np.uint8))
    assert [p[1] for p in _packets(receiver, 17)] == [*range(1, 16), 1, 2]


def test_send_nonblocking_returns_0_when_the_whole_frame_went(client: DDPClient, receiver: socket.socket) -> None:
    assert client.send_nonblocking(np.zeros(2000, dtype=np.uint8)) == 0
    packets = _packets(receiver, 2)
    assert [p[0] & _PUSH for p in packets] == [0, _PUSH]


def test_push_every_packet_sets_the_flag_on_each(client: DDPClient, receiver: socket.socket) -> None:
    client.send_nonblocking(np.zeros(2000, dtype=np.uint8), push_every_packet=True)
    assert [p[0] & _PUSH for p in _packets(receiver, 2)] == [_PUSH, _PUSH]


def test_sending_before_connect_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="not connected"):
        DDPClient("127.0.0.1").send(np.zeros(3, dtype=np.uint8))
