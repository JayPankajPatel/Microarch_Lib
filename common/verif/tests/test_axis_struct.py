"""Unit tests for axis_struct (pure Python, no simulator).

Run: pixi run pytest common/verif/tests
"""

import pytest

from axis_struct import (
    AxisReq,
    AxisReqLayout,
    pack_req,
    pack_resp,
    unpack_req,
    unpack_resp,
)


def test_signed_is_required():
    with pytest.raises(TypeError):
        AxisReqLayout(16)  # ty: ignore[missing-argument]  (the point of the test)


def test_layout_matches_verilator_observation():
    # Measured on Verilator 5.052 with MA_AXIS_ALL(audio, logic signed [15:0]):
    # {tvalid=1, tlast=0, tdata=-5} reads back as 0x2FFFB.
    layout = AxisReqLayout(data_width=16, signed=True)
    assert layout.width == 18
    assert pack_req(layout, tvalid=True, tlast=False, tdata=-5) == 0x2FFFB
    assert unpack_req(layout, 0x2FFFB) == AxisReq(tvalid=True, tlast=False, tdata=-5)


def test_same_bits_differ_by_signedness():
    raw = 0x2FFFB
    assert unpack_req(AxisReqLayout(16, signed=True), raw).tdata == -5
    assert unpack_req(AxisReqLayout(16, signed=False), raw).tdata == 0xFFFB


@pytest.mark.parametrize("signed", [True, False])
@pytest.mark.parametrize("width", [1, 3, 8])
def test_round_trip_exhaustive(width, signed):
    layout = AxisReqLayout(width, signed=signed)
    for tdata in range(layout.tdata_min, layout.tdata_max + 1):
        for tvalid in (False, True):
            for tlast in (False, True):
                v = pack_req(layout, tvalid=tvalid, tlast=tlast, tdata=tdata)
                assert 0 <= v < (1 << layout.width)
                assert unpack_req(layout, v) == AxisReq(tvalid, tlast, tdata)


@pytest.mark.parametrize(
    "signed,bad", [(True, 128), (True, -129), (False, -1), (False, 256)]
)
def test_out_of_range_tdata_raises(signed, bad):
    with pytest.raises(ValueError):
        pack_req(AxisReqLayout(8, signed=signed), tvalid=True, tlast=False, tdata=bad)


def test_unpack_rejects_oversized_value():
    with pytest.raises(ValueError):
        unpack_req(AxisReqLayout(8, signed=False), 1 << 10)


def test_from_handle_derives_width():
    class FakeHandle:
        _name = "s_req"

        def __len__(self):
            return 26

    layout = AxisReqLayout.from_handle(FakeHandle(), signed=True)
    assert layout == AxisReqLayout(24, signed=True)


def test_from_handle_rejects_too_narrow():
    class Narrow:
        _name = "s_resp"

        def __len__(self):
            return 1

    with pytest.raises(ValueError):
        AxisReqLayout.from_handle(Narrow(), signed=False)


def test_resp_round_trip():
    assert pack_resp(tready=True) == 1 and pack_resp(tready=False) == 0
    assert unpack_resp(1) is True and unpack_resp(0) is False
    with pytest.raises(ValueError):
        unpack_resp(2)
