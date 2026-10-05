"""Pack and unpack ``MA_AXIS_*`` struct ports as cocotb sees them.

cocotb on Verilator exposes a packed-struct port only as one flat vector:
``dut.s_req`` exists, ``dut.s_req.tvalid`` and ``dut.s_req.payload.tdata`` do
not (measured with Verilator 5.052; see docs/adr/0023). These helpers convert
between that flat integer and named fields.

The bit layout mirrors the field declaration order in
``common/rtl/ma_axis_typedef.svh`` -- first declared field is the MSB::

    <name>_axis_req_t  = { tvalid, payload }       payload = { tlast, tdata }
                       = { tvalid, tlast, tdata[W-1:0] }   (W + 2 bits)
    <name>_axis_resp_t = { tready }                         (1 bit)

If the field order in the macros changes, this file must change with it.

Signedness is never inferred: the flat vector carries no type information,
so every layout must state ``signed=True`` or ``signed=False``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, SupportsInt


@dataclass(frozen=True)
class AxisReqLayout:
    """Bit layout of an ``<name>_axis_req_t`` vector.

    Args:
        data_width: Width of ``tdata`` in bits.
        signed: Whether ``tdata`` is two's complement. Required -- there is
            no default, because the vector cannot tell signed from unsigned.
    """

    data_width: int
    signed: bool

    def __post_init__(self) -> None:
        if self.data_width < 1:
            raise ValueError(f"data_width must be >= 1, got {self.data_width}")

    @property
    def width(self) -> int:
        """Total vector width: tvalid + tlast + tdata."""
        return self.data_width + 2

    @property
    def tvalid_bit(self) -> int:
        return self.data_width + 1

    @property
    def tlast_bit(self) -> int:
        return self.data_width

    @property
    def tdata_min(self) -> int:
        return -(1 << (self.data_width - 1)) if self.signed else 0

    @property
    def tdata_max(self) -> int:
        if self.signed:
            return (1 << (self.data_width - 1)) - 1
        return (1 << self.data_width) - 1

    @classmethod
    def from_handle(cls, handle: Any, *, signed: bool) -> AxisReqLayout:
        """Derive the layout from a cocotb handle to a req port.

        The data width is ``len(handle) - 2`` (tvalid and tlast are one bit
        each). ``signed`` must still be given explicitly.
        """
        width = len(handle)
        if width < 3:
            raise ValueError(
                f"{getattr(handle, '_name', 'handle')} is {width} bits; an "
                "axis req vector is at least 3 bits (tvalid, tlast, tdata)"
            )
        return cls(data_width=width - 2, signed=signed)


@dataclass(frozen=True)
class AxisReq:
    """Decoded fields of an ``<name>_axis_req_t`` vector."""

    tvalid: bool
    tlast: bool
    tdata: int


def pack_req(layout: AxisReqLayout, *, tvalid: bool, tlast: bool, tdata: int) -> int:
    """Build the flat req vector value to assign to e.g. ``dut.s_req.value``.

    ``tdata`` must be in range for the layout: ``[-2**(W-1), 2**(W-1)-1]``
    when signed, ``[0, 2**W-1]`` when unsigned. Out-of-range values raise
    instead of being silently truncated.
    """
    if not layout.tdata_min <= tdata <= layout.tdata_max:
        kind = "signed" if layout.signed else "unsigned"
        raise ValueError(
            f"tdata={tdata} out of range for {layout.data_width}-bit {kind} "
            f"[{layout.tdata_min}, {layout.tdata_max}]"
        )
    raw = tdata & ((1 << layout.data_width) - 1)  # two's complement if negative
    return (int(bool(tvalid)) << layout.tvalid_bit) | (int(bool(tlast)) << layout.tlast_bit) | raw


def unpack_req(layout: AxisReqLayout, value: SupportsInt) -> AxisReq:
    """Decode a flat req vector, e.g. ``unpack_req(layout, dut.m_req.value)``.

    ``value`` may be an ``int`` or anything ``int()`` accepts, such as a
    cocotb ``LogicArray``. A vector containing X/Z bits cannot be converted
    and raises from ``int()``; resolve or wait for a known value first.
    """
    v = int(value)
    if not 0 <= v < (1 << layout.width):
        raise ValueError(f"value 0x{v:X} does not fit in {layout.width} bits")
    raw = v & ((1 << layout.data_width) - 1)
    if layout.signed and raw >> (layout.data_width - 1):
        tdata = raw - (1 << layout.data_width)  # sign-extend
    else:
        tdata = raw
    return AxisReq(
        tvalid=bool((v >> layout.tvalid_bit) & 1),
        tlast=bool((v >> layout.tlast_bit) & 1),
        tdata=tdata,
    )


def pack_resp(*, tready: bool) -> int:
    """Build the flat ``<name>_axis_resp_t`` value (``{ tready }``)."""
    return int(bool(tready))


def unpack_resp(value: SupportsInt) -> bool:
    """Decode a flat ``<name>_axis_resp_t`` value; returns ``tready``."""
    v = int(value)
    if v not in (0, 1):
        raise ValueError(f"resp value {v} does not fit in 1 bit")
    return bool(v)
