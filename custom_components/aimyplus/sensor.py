from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import CURRENCY_DOLLAR
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SITE_SLUG, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([AimyPlusAmountOwingSensor(coordinator, entry)])


class AimyPlusAmountOwingSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "Amount Owing"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = CURRENCY_DOLLAR

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        slug = entry.data[CONF_SITE_SLUG]
        display_name = slug.capitalize()
        self._attr_unique_id = f"{entry.entry_id}_amount_owing"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, slug)},
            name=display_name,
            manufacturer="Aimy Plus",
            model="Site",
        )

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("amount_owing")
