"""SacnSource: received frames are written by the event loop, not the receiver thread."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from rasl.config.build import parse_config


async def test_a_packet_from_the_receiver_thread_is_written_on_the_event_loop() -> None:
    plan = parse_config("graph {\n    node SacnSource input { universes 1; }\n}\n")
    source = plan.nodes["input"]
    # What start() sets, without opening a socket
    source._ctx = object()
    source._loop = asyncio.get_running_loop()
    source._receiver = object()

    written_on: list[int] = []
    publish = source._publish

    def recording_publish(*args):
        written_on.append(threading.get_ident())
        publish(*args)

    source._publish = recording_publish
    packet = SimpleNamespace(dmxData=[255] * 512, universe=1)
    receiver = threading.Thread(target=source._make_listener(1), args=(packet,))
    receiver.start()
    receiver.join()

    assert written_on == []  # nothing written from the receiver's thread
    for _ in range(10):
        await asyncio.sleep(0)
        if written_on:
            break
    assert written_on == [threading.get_ident()]  # written by the loop's own thread
