"""Register the optional Cube S weekly Lovelace card.

The DHW custom card was retired for 1.2.0. Keep the weekly timeline;
do not alter dashboards or their saved cards automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_ROOT = Path(__file__).parent / "www"
_CARD_PATH = "/ariston_cube/ariston-cube-weekly-card.js"
_CARD_RESOURCE = _CARD_PATH + "?v=1.2.0"
_FLAG = "ariston_cube_frontend_registered"


async def async_register_weekly_card(hass) -> None:
    """Serve and register only the Cube S weekly timeline card."""
    from homeassistant.components.http import StaticPathConfig

    if hass.data.get(_FLAG):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(_CARD_PATH, str(_ROOT / "ariston-cube-weekly-card.js"), False),
    ])
    hass.data[_FLAG] = True
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE

        lovelace = hass.data.get(LOVELACE_DATA)
        if lovelace is None or lovelace.resource_mode != MODE_STORAGE:
            _LOGGER.info(
                "Ariston Cube weekly card served locally; YAML-mode users "
                "must register the resource"
            )
            return
        resources = lovelace.resources
        await resources.async_get_info()
        # Reuse an existing resource instead of creating a duplicate.
        # Updating its query version busts the browser's cached read-only JS.
        existing = next(
            (
                item for item in resources.async_items()
                if item.get("url", "").split("?")[0] == _CARD_PATH
            ),
            None,
        )
        if existing is None:
            await resources.async_create_item({
                "res_type": "module", "url": _CARD_RESOURCE
            })
        elif existing.get("url") != _CARD_RESOURCE:
            await resources.async_update_item(
                existing["id"], {"res_type": "module", "url": _CARD_RESOURCE}
            )
        _LOGGER.info("Ariston Cube weekly Lovelace card resource available")
    except (ImportError, AttributeError, RuntimeError, ValueError) as exc:
        _LOGGER.warning(
            "Ariston Cube weekly card registration skipped: %s", type(exc).__name__
        )
