"""Bundled Lovelace card for the Snapmaker U1 integration.

Serves ``www/snapmaker-u1-card.js`` from the integration and loads it on every
dashboard, so the ``custom:snapmaker-u1-card`` card works without adding a
dashboard resource by hand. A websocket command tells the card which entity
plays which role, so it never has to guess from entity IDs the user may have
renamed.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "snapmaker-u1-card.js"
CARD_URL_BASE = f"/{DOMAIN}_static"
CARD_URL = f"{CARD_URL_BASE}/{CARD_FILENAME}"
WS_TYPE_ENTITIES = f"{DOMAIN}/entities"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card and add it to every dashboard (call once)."""
    www = Path(__file__).parent / "www"
    manifest = json.loads(
        await hass.async_add_executor_job(
            (Path(__file__).parent / "manifest.json").read_text
        )
    )
    version = manifest.get("version", "0")

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(www), False)]
        )
    except ImportError:  # Home Assistant < 2024.6
        hass.http.register_static_path(CARD_URL_BASE, str(www), False)

    # Version query string so browsers pick up a new card after an update.
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    websocket_api.async_register_command(hass, ws_entities)


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_ENTITIES})
@callback
def ws_entities(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return every Snapmaker U1 printer with its entities keyed by role.

    Roles are ``<domain>.<description key>``, e.g. ``sensor.print_progress``,
    ``sensor.extruder1_temperature`` or ``number.bed_target``.
    """
    registry = er.async_get(hass)
    printers: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        prefix = f"{entry.data.get('host', '')}_"
        entities: dict[str, str] = {}
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.disabled_by or not reg_entry.unique_id.startswith(prefix):
                continue
            role = f"{reg_entry.domain}.{reg_entry.unique_id[len(prefix):]}"
            entities[role] = reg_entry.entity_id
        coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        printers.append(
            {
                "entry_id": entry.entry_id,
                "title": (
                    coordinator.printer_name if coordinator is not None else entry.title
                ),
                "entities": entities,
            }
        )
    connection.send_result(msg["id"], {"printers": printers})
