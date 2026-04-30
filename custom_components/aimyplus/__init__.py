from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AimyPlusApi
from .const import DOMAIN, CONF_SITE_SLUG, CONF_USERNAME, CONF_PASSWORD, CONF_PARENT_ID
from .coordinator import AimyPlusCoordinator

PLATFORMS = ["calendar", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_create_clientsession(
        hass,
        cookie_jar=CookieJar(unsafe=True),
    )

    api = AimyPlusApi(
        session=session,
        site_slug=entry.data[CONF_SITE_SLUG],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        parent_id=entry.data.get(CONF_PARENT_ID),
    )

    coordinator = AimyPlusCoordinator(hass, entry, api)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        await session.close()
        raise ConfigEntryNotReady(f"Aimy Plus setup failed: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id)
    await data["session"].close()

    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    return True
