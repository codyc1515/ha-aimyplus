from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AimyPlusApi
from .const import DOMAIN, CONF_SITE_SLUG, CONF_USERNAME, CONF_PASSWORD

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
    )

    try:
        await api.get_parent_id()
    except Exception as err:
        raise ConfigEntryNotReady(f"Aimy Plus setup failed: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True