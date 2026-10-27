"""Register the two optional bundled Lovelace cards for Ariston Cube.

No dashboard layout is modified. In storage mode the resources are
automatically created if absent; YAML mode requires explicit configuration.
Card registration never blocks boiler setup.
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_ROOT = Path(__file__).parent / "www"
_CARD_PATH = "/ariston_cube/ariston-cube-weekly-card.js"
_CARD_RESOURCE = _CARD_PATH + "?v=1.0.0"
_ACS_CARD_PATH = "/ariston_cube/ariston-cube-acs-card.js"
_ACS_CARD_RESOURCE = _ACS_CARD_PATH + "?v=1.0.0"
_FLAG = "ariston_cube_frontend_registered"


async def async_register_weekly_card(hass) -> None:
    """Register read-only weekly and ACS UI cards, without editing dashboards."""
    from homeassistant.components.http import StaticPathConfig

    if hass.data.get(_FLAG):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(_CARD_PATH, str(_ROOT / "ariston-cube-weekly-card.js"), False),
        StaticPathConfig(_ACS_CARD_PATH, str(_ROOT / "ariston-cube-acs-card.js"), False),
    ])
    hass.data[_FLAG] = True
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE

        lovelace = hass.data.get(LOVELACE_DATA)
        if lovelace is None or lovelace.resource_mode != MODE_STORAGE:
            _LOGGER.info(
                "Ariston Cube cards served locally; YAML-mode users must register resources"
            )
            return
        resources = lovelace.resources
        await resources.async_get_info()
        existing = {
            item.get("url", "").split("?")[0]
            for item in resources.async_items()
        }
        for url, resource in (
            (_CARD_PATH, _CARD_RESOURCE), (_ACS_CARD_PATH, _ACS_CARD_RESOURCE)
        ):
            if url not in existing:
                await resources.async_create_item({
                    "res_type": "module", "url": resource
                })
        _LOGGER.info("Ariston Cube Lovelace card resources available")
    except (ImportError, AttributeError, RuntimeError, ValueError) as exc:
        _LOGGER.warning(
            "Ariston Cube Lovelace card registration skipped: %s", type(exc).__name__
        )
