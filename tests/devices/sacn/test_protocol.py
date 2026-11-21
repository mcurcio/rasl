"""E1.31 codec, sequence rule and universe arbitration (rasl-2lg, design 4.1)."""

from __future__ import annotations

import random

import pytest
from sacn.messages.data_packet import DataPacket

from rasl.devices.sacn.protocol import (
    E131_PORT,
    LOSS_TIMEOUT_S,
    DataFrame,
    SequenceTracker,
    SourceInfo,
    UniverseArbiter,
    Verdict,
    decode,
    encode_data,
    multicast_group,
    sequence_accepts,
)

CID_A = bytes(range(16))
CID_B = bytes(range(16, 32))
CID_C = bytes(range(32, 48))


def _packet(**overrides) -> bytes:
    args = dict(cid=CID_A, universe=1, sequence=0, priority=100, source_name="rasl", slots=b"\x01\x02\x03")
    args.update(overrides)
    return encode_data(**args)


def _frame(cid: bytes = CID_A, sequence: int = 0, priority: int = 100, **overrides) -> DataFrame:
    fields = dict(
        cid=cid,
        universe=1,
        priority=priority,
        sequence=sequence,
        source_name="src",
        start_code=0,
        slots=b"\x10\x20",
        terminated=False,
        preview=False,
        sync_address=0,
    )
    fields.update(overrides)
    return DataFrame(**fields)


# --- constants and multicast ---------------------------------------------------------------


def test_constants() -> None:
    assert E131_PORT == 5568
    assert LOSS_TIMEOUT_S == 2.5


@pytest.mark.parametrize(
    ("universe", "group"),
    [(1, "239.255.0.1"), (255, "239.255.0.255"), (256, "239.255.1.0"), (63999, "239.255.249.255")],
)
def test_multicast_group(universe: int, group: str) -> None:
    assert multicast_group(universe) == group


@pytest.mark.parametrize("universe", [0, -1, 64000])
def test_multicast_group_rejects_universes_without_a_group(universe: int) -> None:
    with pytest.raises(ValueError):
        multicast_group(universe)


# --- sequence rule -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("last", "new", "accepted"),
    [
        (5, 250, False),  # d = -11
        (250, 5, True),  # d = +11
        (100, 81, False),  # d = -19
        (100, 100, False),  # d = 0
        (100, 80, True),  # d = -20
        (100, 101, True),  # d = +1
        (255, 0, True),  # wrap forward
        (0, 255, False),  # d = -1 across the wrap
        (10, 246, True),  # d = -20 across the wrap
        (10, 247, False),  # d = -19 across the wrap
        (0, 128, True),  # d = -128
        (0, 127, True),  # d = +127
    ],
)
def test_sequence_accepts(last: int, new: int, accepted: bool) -> None:
    assert sequence_accepts(last, new) is accepted


def test_sequence_tracker_accepts_the_first_packet_and_is_per_cid() -> None:
    tracker = SequenceTracker()
    assert tracker.accept(CID_A, 200)
    assert tracker.accept(CID_B, 10)  # independent of CID_A's 200
    assert not tracker.accept(CID_A, 200)
    assert tracker.accept(CID_B, 11)
    assert tracker.accept(CID_A, 201)
    assert not tracker.accept(CID_B, 11)


def test_sequence_tracker_does_not_record_rejected_numbers() -> None:
    tracker = SequenceTracker()
    assert tracker.accept(CID_A, 50)
    assert not tracker.accept(CID_A, 45)
    assert tracker.accept(CID_A, 51)  # still compared against 50


def test_sequence_tracker_forget_makes_the_next_packet_a_first_packet() -> None:
    tracker = SequenceTracker()
    assert tracker.accept(CID_A, 50)
    tracker.forget(CID_A)
    assert tracker.accept(CID_A, 50)
    tracker.forget(CID_C)  # unknown CID: no error


# --- encode / decode -----------------------------------------------------------------------


def test_round_trip() -> None:
    raw = encode_data(
        CID_A, 7, 42, 150, "Wohnzimmer ✓", bytes(range(200)), terminated=True, sync_address=9, start_code=0
    )
    assert len(raw) == 126 + 200
    assert decode(raw) == DataFrame(
        cid=CID_A,
        universe=7,
        priority=150,
        sequence=42,
        source_name="Wohnzimmer ✓",
        start_code=0,
        slots=bytes(range(200)),
        terminated=True,
        preview=False,
        sync_address=9,
    )


def test_three_slots_decode_to_three_slots() -> None:
    frame = decode(_packet(slots=b"\x0a\x0b\x0c"))
    assert frame is not None
    assert frame.slots == b"\x0a\x0b\x0c"


def test_zero_slots_round_trip() -> None:
    frame = decode(_packet(slots=b""))
    assert frame is not None
    assert frame.slots == b""


def test_universe_zero_round_trips() -> None:
    frame = decode(_packet(universe=0))
    assert frame is not None
    assert frame.universe == 0


def test_per_address_priority_start_code_is_flagged() -> None:
    frame = decode(_packet(start_code=0xDD, slots=bytes([100] * 512)))
    assert frame is not None
    assert frame.start_code == 0xDD
    assert len(frame.slots) == 512


def test_preview_bit_decodes() -> None:
    raw = bytearray(_packet())
    raw[112] |= 0x80
    frame = decode(bytes(raw))
    assert frame is not None
    assert frame.preview and not frame.terminated


@pytest.mark.parametrize("universe", [1, 0x1234, 63999])
def test_matches_the_sacn_library_byte_for_byte(universe: int) -> None:
    slots = bytes((i * 7) & 0xFF for i in range(512))
    library = bytes(
        DataPacket(
            cid=tuple(CID_A),
            sourceName="rasl oracle",
            universe=universe,
            dmxData=tuple(slots),
            priority=120,
            sequence=77,
            sync_universe=3,
        ).getBytes()
    )
    ours = encode_data(CID_A, universe, 77, 120, "rasl oracle", slots, sync_address=3)
    assert ours == library


def test_matches_the_sacn_library_for_a_terminated_packet() -> None:
    slots = bytes(512)
    library = bytes(
        DataPacket(
            cid=tuple(CID_B), sourceName="x", universe=5, dmxData=tuple(slots), streamTerminated=True
        ).getBytes()
    )
    assert encode_data(CID_B, 5, 0, 100, "x", slots, terminated=True) == library


def test_library_decodes_our_packet() -> None:
    packet = DataPacket.make_data_packet(_packet(universe=9, sequence=3, slots=bytes(range(10))))
    assert packet.universe == 9
    assert packet.sequence == 3
    assert packet.sourceName == "rasl"
    assert packet.dmxData[:10] == tuple(range(10))


@pytest.mark.parametrize(
    "overrides",
    [
        dict(cid=b"\x00" * 15),
        dict(universe=-1),
        dict(universe=64000),
        dict(sequence=-1),
        dict(sequence=256),
        dict(priority=-1),
        dict(priority=201),
        dict(source_name="x" * 64),
        dict(source_name="✓" * 22),  # 66 bytes in UTF-8
        dict(slots=bytes(513)),
        dict(sync_address=64000),
        dict(start_code=256),
    ],
)
def test_encode_rejects_bad_arguments(overrides: dict) -> None:
    with pytest.raises(ValueError):
        _packet(**overrides)


def test_encode_accepts_a_63_byte_name_and_512_slots() -> None:
    frame = decode(_packet(source_name="n" * 63, slots=bytes(512)))
    assert frame is not None
    assert frame.source_name == "n" * 63
    assert len(frame.slots) == 512


def _patched(raw: bytes, offset: int, value: bytes) -> bytes:
    return raw[:offset] + value + raw[offset + len(value) :]


def _sync_packet() -> bytes:
    # Root layer (extended vector 0x08) + synchronization framing layer: 49 bytes
    raw = bytearray(b"\x00\x10\x00\x00" + b"ASC-E1.17\x00\x00\x00")
    raw += (0x7000 | 33).to_bytes(2, "big") + b"\x00\x00\x00\x08" + CID_A
    raw += (0x7000 | 11).to_bytes(2, "big") + b"\x00\x00\x00\x01" + bytes([5]) + b"\x00\x01" + b"\x00\x00"
    assert len(raw) == 49
    return bytes(raw)


def _discovery_packet() -> bytes:
    universes = b"\x00\x01\x00\x02"
    total = 120 + len(universes)
    raw = bytearray(b"\x00\x10\x00\x00" + b"ASC-E1.17\x00\x00\x00")
    raw += (0x7000 | (total - 16)).to_bytes(2, "big") + b"\x00\x00\x00\x08" + CID_A
    raw += (0x7000 | (total - 38)).to_bytes(2, "big") + b"\x00\x00\x00\x02" + b"disc".ljust(64, b"\x00")
    raw += b"\x00\x00\x00\x00"
    raw += (0x7000 | (total - 112)).to_bytes(2, "big") + b"\x00\x00\x00\x01" + b"\x00\x00" + universes
    assert len(raw) == total
    return bytes(raw)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(_patched(_packet(), 113, (64000).to_bytes(2, "big")), id="universe 64000"),
        pytest.param(_patched(_packet(), 108, bytes([250])), id="priority 250"),
        pytest.param(_sync_packet(), id="sync packet"),
        pytest.param(_discovery_packet(), id="discovery packet"),
        pytest.param(_packet()[:-1], id="one byte short"),
        pytest.param(_packet()[:125], id="no start code"),
        pytest.param(b"", id="empty"),
        pytest.param(_patched(_packet(), 4, b"ASC-E1.18"), id="wrong identifier"),
        pytest.param(_patched(_packet(), 0, b"\x00\x11"), id="wrong preamble"),
        pytest.param(_patched(_packet(), 21, b"\x08"), id="extended root vector"),
        pytest.param(_patched(_packet(), 43, b"\x01"), id="wrong framing vector"),
        pytest.param(_patched(_packet(), 117, b"\x01"), id="wrong DMP vector"),
        pytest.param(_patched(_packet(), 118, b"\xa0"), id="wrong address type"),
        pytest.param(_patched(_packet(), 123, b"\x00\x00"), id="property count 0"),
        pytest.param(_patched(_packet(), 123, b"\x02\x02"), id="property count 514"),
        pytest.param(_patched(_packet(), 123, b"\x00\x03"), id="count disagrees with PDU lengths"),
        pytest.param(_patched(_packet(), 16, b"\x70\x00"), id="root length wrong"),
        pytest.param(_patched(_packet(), 38, b"\x60\x5b"), id="framing flags wrong"),
    ],
)
def test_decode_returns_none(raw: bytes) -> None:
    assert decode(raw) is None


def test_decode_ignores_bytes_after_the_root_pdu() -> None:
    frame = decode(_packet(slots=b"\x01\x02\x03") + b"\xff\xff")
    assert frame is not None
    assert frame.slots == b"\x01\x02\x03"


def test_decode_replaces_a_name_that_is_not_utf8() -> None:
    frame = decode(_patched(_packet(), 44, b"caf\xe9\xff\x00junk"))
    assert frame is not None
    assert frame.source_name == "caf��"


def test_decode_stops_the_name_at_the_first_nul() -> None:
    frame = decode(_patched(_packet(), 44, b"ab\x00cd"))
    assert frame is not None
    assert frame.source_name == "ab"


def test_decode_never_raises_on_random_or_mutated_input() -> None:
    rng = random.Random(0x5AC4)
    for _ in range(3000):
        result = decode(rng.randbytes(rng.randrange(0, 700)))
        assert result is None or isinstance(result, DataFrame)
    valid = _packet(slots=bytes(range(64)))
    for _ in range(3000):
        raw = bytearray(valid)
        for _ in range(rng.randrange(1, 6)):
            raw[rng.randrange(len(raw))] = rng.randrange(256)
        if rng.random() < 0.3:
            raw = raw[: rng.randrange(len(raw) + 1)]
        result = decode(bytes(raw))
        assert result is None or isinstance(result, DataFrame)


def test_decode_tolerates_non_bytes() -> None:
    assert decode("not bytes") is None  # type: ignore[arg-type]
    assert decode(bytearray(_packet())) is not None
    assert decode(memoryview(_packet())) is not None


# --- arbitration ---------------------------------------------------------------------------


def test_first_source_wins_and_identical_data_is_data_each_time() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.winner is None
    for seq in range(5):
        assert arbiter.accept(_frame(sequence=seq), now=seq * 0.025) is Verdict.DATA
    assert arbiter.winner == SourceInfo(cid=CID_A, name="src", priority=100)


def test_out_of_order_packet_is_ignored() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(sequence=10), now=0.0) is Verdict.DATA
    assert arbiter.accept(_frame(sequence=10), now=0.1) is Verdict.IGNORED
    assert arbiter.accept(_frame(sequence=5), now=0.2) is Verdict.IGNORED
    assert arbiter.accept(_frame(sequence=11), now=0.3) is Verdict.DATA


def test_higher_priority_wins() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(CID_A, priority=100), now=0.0) is Verdict.DATA
    assert arbiter.accept(_frame(CID_B, priority=150), now=0.1) is Verdict.DATA
    assert arbiter.winner is not None and arbiter.winner.cid == CID_B
    assert arbiter.accept(_frame(CID_A, sequence=1, priority=100), now=0.2) is Verdict.IGNORED
    assert arbiter.accept(_frame(CID_B, sequence=1, priority=150), now=0.3) is Verdict.DATA


def test_equal_priority_first_seen_holds() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(CID_A), now=0.0) is Verdict.DATA
    for seq in range(1, 5):
        assert arbiter.accept(_frame(CID_B, sequence=seq), now=seq) is Verdict.IGNORED
        assert arbiter.accept(_frame(CID_A, sequence=seq), now=seq) is Verdict.DATA
    assert arbiter.winner is not None and arbiter.winner.cid == CID_A


def test_winner_lowering_its_priority_hands_over() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(CID_A, priority=150), now=0.0)
    arbiter.accept(_frame(CID_B, priority=100), now=0.0)
    assert arbiter.accept(_frame(CID_A, sequence=1, priority=50), now=0.1) is Verdict.IGNORED
    assert arbiter.winner is not None and arbiter.winner.cid == CID_B


def test_lower_source_takes_over_after_lazy_expiry() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(CID_A, priority=150), now=0.0) is Verdict.DATA
    assert arbiter.accept(_frame(CID_B, priority=100), now=0.0) is Verdict.IGNORED
    assert arbiter.accept(_frame(CID_B, sequence=1, priority=100), now=1.0) is Verdict.IGNORED
    # A last sent at 0.0; at exactly 2.5 s it is not yet lost
    assert arbiter.accept(_frame(CID_B, sequence=2, priority=100), now=2.5) is Verdict.IGNORED
    assert arbiter.accept(_frame(CID_B, sequence=3, priority=100), now=2.6) is Verdict.DATA
    assert arbiter.winner is not None and arbiter.winner.cid == CID_B
    # A returns: higher priority, it wins again and starts a fresh sequence record
    assert arbiter.accept(_frame(CID_A, sequence=0, priority=150), now=3.0) is Verdict.DATA


def test_equal_priority_source_takes_over_after_expiry() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(CID_A), now=0.0)
    arbiter.accept(_frame(CID_B), now=1.0)
    assert arbiter.accept(_frame(CID_B, sequence=1), now=2.6) is Verdict.DATA


def test_expire_reports_the_loss_of_the_last_source() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(CID_A), now=0.0)
    assert arbiter.expire(2.5) is False
    assert arbiter.winner is not None
    assert arbiter.expire(2.6) is True
    assert arbiter.winner is None
    assert arbiter.expire(10.0) is False


def test_three_terminations_from_the_winner_give_one_terminated() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(sequence=0), now=0.0) is Verdict.DATA
    verdicts = [arbiter.accept(_frame(sequence=s, terminated=True), now=0.1) for s in (1, 2, 3)]
    assert verdicts == [Verdict.TERMINATED, Verdict.IGNORED, Verdict.IGNORED]
    assert arbiter.winner is None
    # The source resumes later with a new stream
    assert arbiter.accept(_frame(sequence=0), now=0.2) is Verdict.DATA


def test_identical_repeated_terminations_give_one_terminated() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(sequence=0), now=0.0)
    verdicts = [arbiter.accept(_frame(sequence=1, terminated=True), now=0.1) for _ in range(3)]
    assert verdicts == [Verdict.TERMINATED, Verdict.IGNORED, Verdict.IGNORED]


def test_termination_from_a_non_winner_is_ignored() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(CID_A, priority=150), now=0.0)
    arbiter.accept(_frame(CID_B, priority=100), now=0.0)
    for seq in (1, 2, 3):
        assert arbiter.accept(_frame(CID_B, sequence=seq, terminated=True), now=0.1) is Verdict.IGNORED
    assert arbiter.winner is not None and arbiter.winner.cid == CID_A
    assert arbiter.accept(_frame(CID_A, sequence=1, priority=150), now=0.2) is Verdict.DATA


def test_termination_from_an_unknown_source_is_ignored() -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(terminated=True), now=0.0) is Verdict.IGNORED
    assert arbiter.winner is None


def test_winner_termination_with_another_live_source_hands_over() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(CID_A, priority=150), now=0.0)
    arbiter.accept(_frame(CID_B, priority=100), now=0.0)
    terminated = _frame(CID_A, sequence=1, priority=150, terminated=True)
    assert arbiter.accept(terminated, now=0.1) is Verdict.IGNORED
    assert arbiter.winner is not None and arbiter.winner.cid == CID_B
    assert arbiter.accept(_frame(CID_B, sequence=1, priority=100), now=0.2) is Verdict.DATA


def test_winner_termination_with_only_expired_others_is_terminated() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(CID_B, priority=100), now=0.0)
    arbiter.accept(_frame(CID_A, priority=150), now=0.0)
    arbiter.accept(_frame(CID_A, sequence=1, priority=150), now=2.0)
    terminated = _frame(CID_A, sequence=2, priority=150, terminated=True)
    assert arbiter.accept(terminated, now=3.0) is Verdict.TERMINATED


def test_terminated_packet_failing_the_sequence_rule_is_ignored() -> None:
    arbiter = UniverseArbiter()
    arbiter.accept(_frame(sequence=10), now=0.0)
    assert arbiter.accept(_frame(sequence=9, terminated=True), now=0.1) is Verdict.IGNORED
    assert arbiter.winner is not None


@pytest.mark.parametrize("overrides", [dict(preview=True), dict(start_code=0xDD)])
def test_preview_and_per_address_priority_are_ignored(overrides: dict) -> None:
    arbiter = UniverseArbiter()
    assert arbiter.accept(_frame(CID_B, sequence=0, priority=200, **overrides), now=0.0) is Verdict.IGNORED
    assert arbiter.winner is None
    assert arbiter.accept(_frame(CID_A, sequence=0), now=0.1) is Verdict.DATA
    assert arbiter.accept(_frame(CID_B, sequence=1, priority=200, **overrides), now=0.2) is Verdict.IGNORED
    assert arbiter.accept(_frame(CID_A, sequence=1, **overrides), now=0.3) is Verdict.IGNORED
    assert arbiter.winner is not None and arbiter.winner.cid == CID_A
    # Ignored packets left the sequence record alone: A's next level packet is in order
    assert arbiter.accept(_frame(CID_A, sequence=1), now=0.4) is Verdict.DATA
