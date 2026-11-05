"""Check that the bundled weekly card retains the timeline and opt-in editor."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "custom_components/ariston_cube/www/ariston-cube-weekly-card.js"
MANUAL = ROOT / "frontend/ariston-cube-weekly-card.js"


def test_bundled_card_and_manual_copy_are_identical():
    card = BUNDLE.read_text(encoding="utf-8")
    assert card == MANUAL.read_text(encoding="utf-8")
    assert 'customElements.define("ariston-cube-weekly-card"' in card
    assert "const weekly = values.map(parseDay)" in card
    assert "const slices = intervals(weekly, index)" in card
    assert "window.customCards.push" in card


def test_weekly_card_has_opt_in_inline_editor_and_single_write_path():
    code = BUNDLE.read_text(encoding="utf-8")
    assert 'this._canEdit' in code
    assert 'Modifica fasce' in code
    assert '"preview_weekly_change"' in code
    assert '"write_weekly_change"' in code
    assert "expected_fingerprint: fingerprint, confirm: true" in code
    assert "this.pending = true" in code
    assert "this.blocked = true" in code
    assert "window.confirm" in code
    assert "undefined, false, true" in code
    assert "fetch(" not in code
    assert "WebSocket" not in code


def test_card_has_manual_local_resource_instructions():
    manual = (ROOT / "frontend/README.md").read_text(encoding="utf-8")
    assert "/local/ariston-cube-weekly-card.js" in manual
    assert "type: custom:ariston-cube-weekly-card" in manual
    assert "YOUR_ACTUAL_WEEKLY_SCHEDULE_ENTITY_ID" in manual
