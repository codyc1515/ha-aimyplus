from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import AimyPlusApi, booking_to_events
from .const import CONF_AMOUNT_OWING, CONF_AMOUNT_OWING_FETCHED_AT, CONF_PARENT_ID

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=6)
AMOUNT_OWING_REFRESH_INTERVAL = timedelta(hours=24)
CALENDAR_LOOKBACK = timedelta(days=4)
CALENDAR_LOOKAHEAD = timedelta(days=3)


class AimyPlusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate Aimy Plus API data for all platforms."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: AimyPlusApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Aimy Plus",
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.api = api

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        now = datetime.now().astimezone()
        calendar_start = now - CALENDAR_LOOKBACK
        calendar_end = now + CALENDAR_LOOKAHEAD

        previous_data = self.data or {}
        entry_amount_owing = self.entry.data.get(CONF_AMOUNT_OWING)
        entry_amount_owing_fetched_at = self._parse_iso_datetime(self.entry.data.get(CONF_AMOUNT_OWING_FETCHED_AT))

        last_amount_owing_fetch = previous_data.get("amount_owing_fetched_at") or entry_amount_owing_fetched_at
        existing_amount_owing = previous_data.get("amount_owing")
        if existing_amount_owing is None:
            existing_amount_owing = entry_amount_owing

        amount_owing_due = (
            last_amount_owing_fetch is None
            or (now - last_amount_owing_fetch) >= AMOUNT_OWING_REFRESH_INTERVAL
            or existing_amount_owing is None
        )

        if amount_owing_due:
            amount_owing = await self.api.get_amount_owing()
            amount_owing_fetched_at = now
        else:
            amount_owing = existing_amount_owing
            amount_owing_fetched_at = last_amount_owing_fetch

        try:
            calendar_events = await self.api.get_calendar_events(calendar_start, calendar_end)
        except Exception:
            _LOGGER.exception("Falling back to booking list because calendar endpoint failed")
            bookings = await self.api.get_bookings()
            calendar_events = []
            for booking in bookings:
                calendar_events.extend(booking_to_events(booking))

        parent_id = self.api.parent_id
        entry_updates: dict[str, Any] = {}
        if parent_id and self.entry.data.get(CONF_PARENT_ID) != parent_id:
            entry_updates[CONF_PARENT_ID] = parent_id
            _LOGGER.debug("Persisted Aimy Plus parent ID %s to config entry", parent_id)

        if amount_owing_due:
            entry_updates[CONF_AMOUNT_OWING] = amount_owing
            entry_updates[CONF_AMOUNT_OWING_FETCHED_AT] = amount_owing_fetched_at.isoformat()

        if entry_updates:
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, **entry_updates},
            )

        return {
            "amount_owing": amount_owing,
            "amount_owing_fetched_at": amount_owing_fetched_at,
            "calendar_events": calendar_events,
            "calendar_window": (calendar_start, calendar_end),
        }
