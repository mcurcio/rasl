"""E1.31-2016 (sACN) data packets, sequence checks and source arbitration, with no I/O.

This module encodes and decodes E1.31 data packets, applies the sequence-number rule of
E1.31 6.7.2 and chooses which source drives a universe. It opens no sockets, starts no
threads and never reads a clock: every time is passed in by the caller, in seconds from a
monotonic clock.

Universe 0 is outside E1.31's range (1..63999) but some devices (WLED) send and expect it, so
`encode_data` and `decode` accept it; it has no multicast group.

Data packet layout (byte offsets; all integers big-endian):

    0-1     preamble size 0x0010        2-3     postamble size 0x0000
    4-15    ACN packet identifier       16-17   root flags (0x7) and length
    18-21   root vector 0x00000004      22-37   CID (16 bytes)
    38-39   framing flags and length    40-43   framing vector 0x00000002
    44-107  source name (UTF-8, NUL padded to 64 bytes)
    108     priority (0..200)           109-110 synchronization address
    111     sequence number             112     options (bit 7 preview, bit 6 terminated,
                                                bit 5 force synchronization)
    113-114 universe                    115-116 DMP flags and length
    117     DMP vector 0x02             118     address and data type 0xa1
    119-120 first property address 0   121-122 address increment 1
    123-124 property value count (1 + number of slots)
    125     DMX start code              126-    slots (0..512 bytes)

Synchronization packet layout (E1.31 6.3; 49 bytes):

    0-37    as above, with root vector 0x00000008
    38-39   framing flags and length    40-43   framing vector 0x00000001
    44      sequence number             45-46   synchronization address (1..63999)
    47-48   reserved (0)

A data packet whose synchronization address is not 0 asks receivers that support
synchronization to hold its data until a synchronization packet for that address arrives
from the same source, so that several universes change at once (E1.31 6.6.1, 11).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

E131_PORT = 5568
"""UDP port that E1.31 senders send to and receivers listen on."""

LOSS_TIMEOUT_S = 2.5
"""Seconds of silence after which a source is treated as lost (E1.31 6.7.1)."""

_ACN_IDENTIFIER = b"ASC-E1.17\x00\x00\x00"
_PREAMBLE = b"\x00\x10\x00\x00"
_VECTOR_ROOT_E131_DATA = 0x00000004
_VECTOR_E131_DATA_PACKET = 0x00000002
_VECTOR_ROOT_E131_EXTENDED = 0x00000008
_VECTOR_E131_EXTENDED_SYNCHRONIZATION = 0x00000001
_SYNC_LEN = 49
_VECTOR_DMP_SET_PROPERTY = 0x02
_DMP_ADDRESS_AND_DATA_TYPE = 0xA1
_HEADER_LEN = 126  # bytes up to and including the start code
_MAX_SLOTS = 512
_MAX_UNIVERSE = 63999
_MAX_PRIORITY = 200
_SOURCE_NAME_LEN = 64
_FLAGS = 0x7

_OPTION_PREVIEW = 0x80
_OPTION_TERMINATED = 0x40

_SEQUENCE_WINDOW = 20


def multicast_group(universe: int) -> str:
    """Return the IPv4 multicast group of a universe, ``239.255.<hi>.<lo>`` (E1.31 9.3.1).

    Raises ValueError for universe 0, which has no group, and for a universe outside 1..63999.
    """
    if not 1 <= universe <= _MAX_UNIVERSE:
        raise ValueError(f"universe {universe} has no multicast group (must be 1..{_MAX_UNIVERSE})")
    return f"239.255.{universe >> 8}.{universe & 0xFF}"


@dataclass(frozen=True, slots=True)
class DataFrame:
    """One decoded E1.31 data packet.

    ``cid`` is the sender's 16-byte component identifier. ``slots`` holds the property values
    after the start code: property value count - 1 bytes (0..512), not padded to 512.
    ``universe`` is 0..63999, ``priority`` 0..200, ``sequence`` 0..255, ``start_code`` 0..255
    (0x00 levels, 0xDD per-address priority), ``sync_address`` 0..65535 (0 means none).
    ``source_name`` is the name up to its first NUL; bytes that are not valid UTF-8 are
    replaced with U+FFFD.
    """

    cid: bytes
    universe: int
    priority: int
    sequence: int
    source_name: str
    start_code: int
    slots: bytes
    terminated: bool
    preview: bool
    sync_address: int


def _flags_and_length(length: int) -> bytes:
    """Return the two-byte PDU flags (0x7) and 12-bit length field for a PDU of ``length`` bytes."""
    return ((_FLAGS << 12) | length).to_bytes(2, "big")


def encode_data(
    cid: bytes,
    universe: int,
    sequence: int,
    priority: int,
    source_name: str,
    slots: bytes,
    *,
    terminated: bool = False,
    sync_address: int = 0,
    start_code: int = 0,
) -> bytes:
    """Encode an E1.31 data packet of 126 + len(slots) bytes, ready to send on UDP.

    ``slots`` (0..512 bytes) follows the start code unpadded. The preview and force
    synchronization options are always clear; ``terminated`` sets the stream-terminated option.

    Raises ValueError when ``cid`` is not 16 bytes, ``universe`` is outside 0..63999,
    ``sequence`` outside 0..255, ``priority`` outside 0..200, ``source_name`` longer than 63
    bytes in UTF-8, ``slots`` longer than 512 bytes, ``sync_address`` outside 0..63999 or
    ``start_code`` outside 0..255.
    """
    cid = bytes(cid)
    slots = bytes(slots)
    if len(cid) != 16:
        raise ValueError(f"cid must be 16 bytes, got {len(cid)}")
    if not 0 <= universe <= _MAX_UNIVERSE:
        raise ValueError(f"universe must be 0..{_MAX_UNIVERSE}, got {universe}")
    if not 0 <= sequence <= 255:
        raise ValueError(f"sequence must be 0..255, got {sequence}")
    if not 0 <= priority <= _MAX_PRIORITY:
        raise ValueError(f"priority must be 0..{_MAX_PRIORITY}, got {priority}")
    name = source_name.encode("utf-8")
    if len(name) > _SOURCE_NAME_LEN - 1:
        raise ValueError(f"source name must be at most 63 bytes in UTF-8, got {len(name)}")
    if len(slots) > _MAX_SLOTS:
        raise ValueError(f"at most {_MAX_SLOTS} slots, got {len(slots)}")
    if not 0 <= sync_address <= _MAX_UNIVERSE:
        raise ValueError(f"sync address must be 0..{_MAX_UNIVERSE}, got {sync_address}")
    if not 0 <= start_code <= 255:
        raise ValueError(f"start code must be 0..255, got {start_code}")

    total = _HEADER_LEN + len(slots)
    options = _OPTION_TERMINATED if terminated else 0
    return b"".join(
        (
            _PREAMBLE,
            _ACN_IDENTIFIER,
            _flags_and_length(total - 16),
            _VECTOR_ROOT_E131_DATA.to_bytes(4, "big"),
            cid,
            _flags_and_length(total - 38),
            _VECTOR_E131_DATA_PACKET.to_bytes(4, "big"),
            name.ljust(_SOURCE_NAME_LEN, b"\x00"),
            bytes((priority,)),
            sync_address.to_bytes(2, "big"),
            bytes((sequence, options)),
            universe.to_bytes(2, "big"),
            _flags_and_length(total - 115),
            bytes((_VECTOR_DMP_SET_PROPERTY, _DMP_ADDRESS_AND_DATA_TYPE)),
            b"\x00\x00\x00\x01",
            (len(slots) + 1).to_bytes(2, "big"),
            bytes((start_code,)),
            slots,
        )
    )


def _pdu_length(raw: bytes, offset: int) -> int | None:
    """Return the 12-bit length at ``offset``, or None when the flags nibble is not 0x7."""
    field = int.from_bytes(raw[offset : offset + 2], "big")
    if field >> 12 != _FLAGS:
        return None
    return field & 0x0FFF


def decode(raw: bytes) -> DataFrame | None:
    """Decode an E1.31 data packet; return None for anything that is not a valid one.

    Never raises. Returns None for synchronization and universe discovery packets (root vector
    0x08), a wrong preamble, identifier or vector, a property value count outside 1..513,
    input shorter than that count needs, PDU lengths that disagree with the count, a universe
    outside 0..63999 and a priority above 200. Bytes after the end of the root PDU are ignored.
    A source name that is not valid UTF-8 is decoded with U+FFFD replacements, not rejected.
    """
    try:
        raw = bytes(raw)
    except (TypeError, ValueError):
        return None
    if len(raw) < _HEADER_LEN:
        return None
    if raw[0:4] != _PREAMBLE or raw[4:16] != _ACN_IDENTIFIER:
        return None
    if int.from_bytes(raw[18:22], "big") != _VECTOR_ROOT_E131_DATA:
        return None
    if int.from_bytes(raw[40:44], "big") != _VECTOR_E131_DATA_PACKET:
        return None
    if (
        raw[117] != _VECTOR_DMP_SET_PROPERTY
        or raw[118] != _DMP_ADDRESS_AND_DATA_TYPE
        or raw[119:123] != b"\x00\x00\x00\x01"
    ):
        return None

    count = int.from_bytes(raw[123:125], "big")
    if not 1 <= count <= _MAX_SLOTS + 1:
        return None
    total = 125 + count
    if len(raw) < total:
        return None
    if (
        _pdu_length(raw, 16) != total - 16
        or _pdu_length(raw, 38) != total - 38
        or _pdu_length(raw, 115) != total - 115
    ):
        return None

    universe = int.from_bytes(raw[113:115], "big")
    if universe > _MAX_UNIVERSE:
        return None
    priority = raw[108]
    if priority > _MAX_PRIORITY:
        return None

    name_field = raw[44:108]
    nul = name_field.find(b"\x00")
    if nul >= 0:
        name_field = name_field[:nul]
    options = raw[112]
    return DataFrame(
        cid=raw[22:38],
        universe=universe,
        priority=priority,
        sequence=raw[111],
        source_name=name_field.decode("utf-8", errors="replace"),
        start_code=raw[125],
        slots=raw[126:total],
        terminated=bool(options & _OPTION_TERMINATED),
        preview=bool(options & _OPTION_PREVIEW),
        sync_address=int.from_bytes(raw[109:111], "big"),
    )


@dataclass(frozen=True, slots=True)
class SyncFrame:
    """A decoded E1.31 synchronization packet.

    Attributes:
        cid: The sender's 16-byte component identifier.
        sync_universe: The synchronization address it releases (1..63999).
        sequence: Its sequence number (0..255), counted per source and address.
    """

    cid: bytes
    sync_universe: int
    sequence: int


def encode_sync(cid: bytes, sync_universe: int, sequence: int) -> bytes:
    """Encode an E1.31 synchronization packet (49 bytes).

    Args:
        cid: The sender's 16-byte component identifier.
        sync_universe: The synchronization address, 1..63999.
        sequence: The sequence number, 0..255.

    Raises:
        ValueError: If an argument is out of range.
    """
    if len(cid) != 16:
        raise ValueError(f"cid must be 16 bytes, got {len(cid)}")
    if not 1 <= sync_universe <= _MAX_UNIVERSE:
        raise ValueError(f"sync_universe must be 1..{_MAX_UNIVERSE}, got {sync_universe}")
    if not 0 <= sequence <= 255:
        raise ValueError(f"sequence must be 0..255, got {sequence}")
    return b"".join(
        (
            _PREAMBLE,
            _ACN_IDENTIFIER,
            _flags_and_length(_SYNC_LEN - 16),
            _VECTOR_ROOT_E131_EXTENDED.to_bytes(4, "big"),
            bytes(cid),
            _flags_and_length(_SYNC_LEN - 38),
            _VECTOR_E131_EXTENDED_SYNCHRONIZATION.to_bytes(4, "big"),
            bytes((sequence,)),
            sync_universe.to_bytes(2, "big"),
            b"\x00\x00",
        )
    )


def decode_sync(raw: bytes) -> SyncFrame | None:
    """Decode an E1.31 synchronization packet; return None for anything that is not one.

    Never raises. Bytes after the 49th are ignored; a synchronization address outside
    1..63999 or disagreeing PDU lengths give None.
    """
    try:
        raw = bytes(raw)
    except (TypeError, ValueError):
        return None
    if len(raw) < _SYNC_LEN:
        return None
    if raw[0:4] != _PREAMBLE or raw[4:16] != _ACN_IDENTIFIER:
        return None
    if int.from_bytes(raw[18:22], "big") != _VECTOR_ROOT_E131_EXTENDED:
        return None
    if int.from_bytes(raw[40:44], "big") != _VECTOR_E131_EXTENDED_SYNCHRONIZATION:
        return None
    if _pdu_length(raw, 16) != _SYNC_LEN - 16 or _pdu_length(raw, 38) != _SYNC_LEN - 38:
        return None
    sync_universe = int.from_bytes(raw[45:47], "big")
    if not 1 <= sync_universe <= _MAX_UNIVERSE:
        return None
    return SyncFrame(cid=raw[22:38], sync_universe=sync_universe, sequence=raw[44])


def sequence_accepts(last: int, new: int) -> bool:
    """Apply E1.31 6.7.2: whether a packet with sequence ``new`` may follow ``last`` (both 0..255).

    The signed distance ``d = ((new - last + 128) % 256) - 128`` is in -128..127. The packet
    is out of order, and rejected, when ``-20 < d <= 0``; it is accepted otherwise, so a
    repeated number is rejected and a jump back of 20 or more is taken as a restarted sender.
    """
    d = ((new - last + 128) % 256) - 128
    return not (-_SEQUENCE_WINDOW < d <= 0)


class SequenceTracker:
    """The last accepted sequence number of each source (CID), for one universe."""

    def __init__(self) -> None:
        self._last: dict[bytes, int] = {}

    def accept(self, cid: bytes, sequence: int) -> bool:
        """Check ``sequence`` (0..255) from ``cid`` and record it when accepted.

        The first packet from a CID, or the first since it was forgotten, is accepted. Returns
        True when the packet is in order (see `sequence_accepts`), False when it should be dropped.
        """
        last = self._last.get(cid)
        if last is not None and not sequence_accepts(last, sequence):
            return False
        self._last[cid] = sequence
        return True

    def forget(self, cid: bytes) -> None:
        """Drop the record of ``cid``, so its next packet is accepted as a first packet."""
        self._last.pop(cid, None)


class Verdict(Enum):
    """What a receiver should do with a frame the arbiter has seen."""

    DATA = "data"
    """The frame comes from the winning source: use its slots."""
    TERMINATED = "terminated"
    """The winning source terminated its stream and no other live source remains."""
    IGNORED = "ignored"
    """Drop the frame: not from the winner, out of order, preview, non-zero start code or a
    repeated termination."""


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """A source sending to a universe: its 16-byte CID, source name and priority (0..200)."""

    cid: bytes
    name: str
    priority: int


@dataclass(slots=True)
class _Source:
    """A live source's arbitration state; times are caller seconds."""

    info: SourceInfo
    first_seen: float
    last_seen: float


class UniverseArbiter:
    """Sequence checking and source arbitration for one universe.

    Policy: the live source with the highest priority wins. At equal priority the source seen
    first holds the universe until it terminates or is silent for more than `LOSS_TIMEOUT_S`.
    Expiry is lazy: it runs at the start of `accept` (or `expire`) against the ``now`` given,
    with no timer. When the winner is lost, the live source with the highest priority, and of
    those the one seen first, wins at once.

    A lower-priority source's in-order level packets keep it live (and are IGNORED), so when
    the winner goes, the next packet from it is DATA. Preview packets and packets whose start
    code is not 0x00 (such as 0xDD per-address priority) are IGNORED and change no state: they
    neither refresh liveness nor advance the sequence record.

    There is no change suppression: every in-order level packet from the winner is DATA, even
    when its slots repeat the previous one.
    """

    def __init__(self) -> None:
        self._sequences = SequenceTracker()
        self._sources: dict[bytes, _Source] = {}
        self._winner: bytes | None = None

    @property
    def winner(self) -> SourceInfo | None:
        """The source that currently drives the universe, or None when there is none.

        Reflects the last `accept` or `expire`; a winner silent since then is still reported
        until one of them runs with a later ``now``.
        """
        if self._winner is None:
            return None
        return self._sources[self._winner].info

    def expire(self, now: float) -> bool:
        """Forget sources silent for more than `LOSS_TIMEOUT_S` at ``now`` (seconds).

        Elects a new winner from the remaining live sources if the winner was among them.
        Returns True when the universe had a winner and now has none, False otherwise.
        """
        had_winner = self._winner is not None
        for cid in [c for c, s in self._sources.items() if now - s.last_seen > LOSS_TIMEOUT_S]:
            self._drop(cid)
        if self._winner is None:
            self._elect()
        return had_winner and self._winner is None

    def accept(self, frame: DataFrame, now: float) -> Verdict:
        """Arbitrate ``frame``, received at ``now`` (seconds, same clock as earlier calls).

        Returns DATA when the frame's slots should be used, TERMINATED once when the winner
        ends its stream and no other live source remains, and IGNORED otherwise (see the class
        docstring). A termination forgets its source and that source's sequence record; its
        slots are never used.
        """
        self.expire(now)
        if frame.preview or frame.start_code != 0x00:
            return Verdict.IGNORED
        cid = frame.cid

        if frame.terminated:
            if cid not in self._sources or not self._sequences.accept(cid, frame.sequence):
                return Verdict.IGNORED
            was_winner = cid == self._winner
            self._drop(cid)
            self._elect()
            if was_winner and self._winner is None:
                return Verdict.TERMINATED
            return Verdict.IGNORED

        if not self._sequences.accept(cid, frame.sequence):
            return Verdict.IGNORED
        info = SourceInfo(cid=cid, name=frame.source_name, priority=frame.priority)
        source = self._sources.get(cid)
        if source is None:
            self._sources[cid] = _Source(info=info, first_seen=now, last_seen=now)
        else:
            source.info = info
            source.last_seen = now

        top = max(s.info.priority for s in self._sources.values())
        if self._winner is None or self._sources[self._winner].info.priority < top:
            self._elect()
        return Verdict.DATA if cid == self._winner else Verdict.IGNORED

    def _drop(self, cid: bytes) -> None:
        """Forget a source and its sequence record; clear the winner if it was that source."""
        self._sources.pop(cid, None)
        self._sequences.forget(cid)
        if cid == self._winner:
            self._winner = None

    def _elect(self) -> None:
        """Make the highest-priority, first-seen live source the winner (None when none is live)."""
        if not self._sources:
            self._winner = None
            return
        self._winner = min(
            self._sources.items(), key=lambda item: (-item[1].info.priority, item[1].first_seen)
        )[0]
