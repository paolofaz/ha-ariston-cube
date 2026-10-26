"""Static checks for optional native Lovelace weekly timetable card."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_card_exposes_single_read_only_custom_element():
    code = (ROOT / "frontend/ariston-cube-weekly-card.js").read_text()
    assert 'customElements.define("ariston-cube-weekly-card"' in code
    assert "const weekly = values.map(parseDay)" in code
    assert "const slices = intervals(weekly, index)" in code
    assert "window.customCards.push" in code
    assert "hass.callService" not in code
    assert "fetch(" not in code
    assert "WebSocket" not in code


def test_card_has_manual_local_resource_instructions():
    manual = (ROOT / "frontend/README.md").read_text()
    assert "/local/ariston-cube-weekly-card.js" in manual
    assert "type: custom:ariston-cube-weekly-card" in manual
    assert "SOSTITUISCI_CON_IL_TUO_ID_REALE" in manual
