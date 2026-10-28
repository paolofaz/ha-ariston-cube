"""Regression contracts for the deliberately reduced v1.3 service catalog.

Home Assistant Actions should show only operationally useful actions, no
retired probes, obsolete unsupported writers or manual gas statistics writes.
"""

import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "ariston_cube"

WEEKLY = {
    "preview_weekly_change", "write_weekly_change",
    "preview_weekly_clone", "clone_weekly_days",
}
READ_ONLY_GAS = {
    "inspect_energy_hour_alignment",
    "inspect_automatic_energy_hour_alignment",
}
PUBLIC = WEEKLY | READ_ONLY_GAS
DEPRECATED = {
    "preview_weekly_slice", "probe_weekly_methods",
    "test_write_weekly_slice", "preview_energy_hour_alignment",
    "apply_energy_hour_alignment",
}


def test_yaml_declares_exactly_six_actions_without_old_test_badges():
    source = (INTEGRATION / "services.yaml").read_text()
    names = set(re.findall(r"^([a-z][a-z_]+):\s*$", source, re.M))
    assert names == PUBLIC
    assert "TEST" not in source.upper()
    assert not DEPRECATED.intersection(names)


def test_runtime_registers_exactly_the_actions_described_in_yaml():
    source = (INTEGRATION / "__init__.py").read_text()
    module = ast.parse(source)
    registered = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "async_register":
            continue
        if not isinstance(func.value, ast.Attribute) or func.value.attr != "services":
            continue
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            registered.append(node.args[1].value)
    assert len(registered) == len(PUBLIC)
    assert set(registered) == PUBLIC
    for name in DEPRECATED:
        assert f'"{name}"' not in source


def test_cloud_writer_is_preserved_but_not_exposed_as_a_test_service():
    init = (INTEGRATION / "__init__.py").read_text()
    gas = (INTEGRATION / "energy_alignment.py").read_text()
    runner = (INTEGRATION / "energy_automation.py").read_text()
    assert "AutomaticEnergyHourRunner" in init
    assert "EnergyHourAligner" in runner
    assert "async_import_statistics" in gas
    assert "async_import_statistics" not in runner
    assert '"inspect_energy_hour_alignment"' in init
    assert '"inspect_automatic_energy_hour_alignment"' in init
    assert '"apply_energy_hour_alignment"' not in init


def test_editor_has_no_legacy_test_action_dependencies():
    bundle = (INTEGRATION / "www" / "ariston-cube-weekly-card.js").read_text()
    manual = (ROOT / "frontend" / "ariston-cube-weekly-card.js").read_text()
    assert bundle == manual
    for name in WEEKLY:
        assert name in bundle
    for name in DEPRECATED:
        assert name not in bundle
    assert 'this.operation = "move"' in bundle
    assert 'if (kind === "move")' in bundle
    assert "expected_fingerprint: fingerprint, confirm: true" in bundle
