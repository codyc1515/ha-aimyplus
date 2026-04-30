from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.dt import as_local

from .const import CONF_SITE_SLUG, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([AimyPlusCalendar(coordinator, entry)])


class AimyPlusCalendar(CoordinatorEntity, CalendarEntity):
    _attr_name = "Calendar"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        slug = entry.data[CONF_SITE_SLUG]
        display_name = slug.capitalize()
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, slug)},
            name=display_name,
            manufacturer="Aimy Plus",
            model="Site",
        )

    @property
    def event(self):
        now = datetime.now().astimezone()
        future_events = [
            event
            for event in (self.coordinator.data or {}).get("calendar_events", [])
            if as_local(event["end"]) >= now
        ]

        if not future_events:
            return None

        next_event = min(future_events, key=lambda event: event["start"])
        return self._to_calendar_event(next_event)

    async def async_get_events(self, hass, start_date, end_date):
        return [
            self._to_calendar_event(event)
            for event in (self.coordinator.data or {}).get("calendar_events", [])
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
