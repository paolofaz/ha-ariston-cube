"""Check local Home Assistant brand image has a valid square PNG header."""

from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def test_brand_icon_is_valid_256px_png():
    payload = (ROOT / "brand" / "icon.png").read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload[12:16] == b"IHDR"
    width, height = struct.unpack(">II", payload[16:24])
    assert (width, height) == (256, 256)
    assert b"tRNS" in payload  # transparent background preserved
    assert len(payload) < 80_000
