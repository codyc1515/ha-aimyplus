from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.util.dt import as_local

from .api import booking_to_events
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


async def async_setup_entry(hass, entry, async_add_entities):
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    async def async_update_data():
        now = datetime.now().astimezone()
        try:
            return await api.get_calendar_events(now - timedelta(days=30), now + timedelta(days=180))
        except Exception:
            _LOGGER.exception("Falling back to booking list because Aimy Plus calendar endpoint failed")
            bookings = await api.get_bookings()
            events = []
            for booking in bookings:
                events.extend(booking_to_events(booking))
            return events

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Aimy Plus calendar",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()
    async_add_entities([AimyPlusCalendar(coordinator, entry, api)])


class AimyPlusCalendar(CoordinatorEntity, CalendarEntity):
    _attr_name = "Aimy Plus"
    _attr_has_entity_name = False

    def __init__(self, coordinator, entry, api):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self.api = api

    @property
    def event(self):
        now = datetime.now().astimezone()
        future_events = [
            event
            for event in self.coordinator.data or []
            if as_local(event["end"]) >= now
        ]

        if not future_events:
            return None

        next_event = min(future_events, key=lambda event: event["start"])
        return self._to_calendar_event(next_event)

    async def async_get_events(self, hass, start_date, end_date):
        try:
            events = await self.api.get_calendar_events(start_date, end_date)
            return [self._to_calendar_event(event) for event in events]
        except Exception:
            _LOGGER.exception("Failed to fetch Aimy Plus calendar range; using cached events")

        return [
            self._to_calendar_event(event)
            for event in self.coordinator.data or []
            if as_local(event["end"]) >= start_date
            and as_local(event["start"]) <= end_date
        ]

    def _to_calendar_event(self, event):
        return CalendarEvent(
            uid=event["uid"],
            summary=event["summary"],
            start=as_local(event["start"]),
            end=as_local(event["end"]),
            description=event.get("description"),
            location=event.get("location"),
        )
