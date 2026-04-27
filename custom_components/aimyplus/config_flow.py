import voluptuous as vol

from homeassistant import config_entries

from .const import (
    DOMAIN,
    CONF_SITE_SLUG,
    CONF_USERNAME,
    CONF_PASSWORD,
    DEFAULT_SITE_SLUG,
)


class AimyPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            slug = user_input[CONF_SITE_SLUG].strip().lower()
            user_input[CONF_SITE_SLUG] = slug

            await self.async_set_unique_id(f"{slug}:{user_input[CONF_USERNAME]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Aimy Plus {slug}",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_SITE_SLUG, default=DEFAULT_SITE_SLUG): str,
                }
            ),
            errors={},
        )
