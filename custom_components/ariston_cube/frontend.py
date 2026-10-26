"""Register bundled Cube S weekly Lovelace card once per Home Assistant instance.

Works with storage-mode resources automatically; YAML resource mode keeps
explicit user configuration. Never make boiler setup depend on frontend UI.
"""

from __future__ import annotations

import logging
from pathlib import Path


_LOGGER = logging.getLogger(__name__)

_CARD_FILE = Path(__file__).parent / "www" / "ariston-cube-weekly-card.js"
_CARD_PATH = "/ariston_cube/ariston-cube-weekly-card.js"
_CARD_RESOURCE = _CARD_PATH + "?v=0.8.6"
_FLAG = "ariston_cube_frontend_registered"


async def async_register_weekly_card(hass) -> None:
    """Serve and expose bundled JS without touching user dashboard layouts."""
    from homeassistant.components.http import StaticPathConfig

    if hass.data.get(_FLAG):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(_CARD_PATH, str(_CARD_FILE), False)
    ])
    hass.data[_FLAG] = True
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE

        lovelace = hass.data.get(LOVELACE_DATA)
        if lovelace is None:
            _LOGGER.info(
                "Ariston Cube weekly card available at %s; "
                "Lovelace not initialized, resource must be added manually",
                _CARD_PATH,
            )
            return
        if lovelace.resource_mode != MODE_STORAGE:
            _LOGGER.info(
                "Ariston Cube weekly card available at %s; "
                "Lovelace YAML resources require manual registration",
                _CARD_PATH,
            )
            return
        resources = lovelace.resources
        await resources.async_get_info()  # ensure storage has been loaded
        registered = resources.async_items()
        # Existing /local resource may still point at an earlier manually
        # copied card. We register a new versioned URL for updates.
        if any(item.get("url", "").split("?")[0] == _CARD_PATH
               for item in registered):
            return
        await resources.async_create_item({
            "res_type": "module", "url": _CARD_RESOURCE
        })
        _LOGGER.info("Ariston Cube weekly card registered automatically")
    except (ImportError, AttributeError, RuntimeError, ValueError) as exc:
        # Only the Lovelace card is optional; cloud entities must still work.
        _LOGGER.warning(
            "Cube S weekly card resource registration was skipped: %s", type(exc).__name__
        )
