"""The eSolar integration."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any, TypedDict, cast

import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MONITORED_SITES, CONF_PV_GRID_DATA, CONF_UPDATE_INTERVAL, DOMAIN
from .esolar import get_esolar_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class ESolarResponse(TypedDict):
    """API response."""

    status: str
    plantList: dict[str, Any]


async def update_listener(hass, entry):
    """Handle options update."""
    _LOGGER.debug(entry.options)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up eSolar from a config entry."""
    coordinator = ESolarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class ESolarCoordinator(DataUpdateCoordinator[ESolarResponse]):
    """Data update coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=CONF_UPDATE_INTERVAL),
            # update_interval=timedelta(seconds=20),
        )
        self._entry = entry
        self.temp = 3

    @property
    def entry_id(self) -> str:
        """Return entry ID."""
        return self._entry.entry_id

    async def _async_update_data(self) -> ESolarResponse:
        """Fetch the latest data from the source."""
        try:
            data = await self.hass.async_add_executor_job(
                get_data, self.hass, self._entry.data, self._entry.options
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except ESolarError as err:
            raise UpdateFailed(str(err)) from err

        return data


class ESolarError(HomeAssistantError):
    """Base error."""


class InvalidAuth(ESolarError):
    """Raised when invalid authentication credentials are provided."""


class APIRatelimitExceeded(ESolarError):
    """Raised when the API rate limit is exceeded."""


class UnknownError(ESolarError):
    """Raised when an unknown error occurs."""


def get_data(
    hass: HomeAssistant, config: Mapping[str, Any], options: Mapping[str, Any]
) -> ESolarResponse:
    """Get data from the API."""

    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    plants = options.get(CONF_MONITORED_SITES)
    use_pv_grid_attributes = options.get(CONF_PV_GRID_DATA)

    try:
        _LOGGER.debug(
            "Fetching data with username %s, for plants %s with pv attributes set to %s",
            username,
            plants,
            use_pv_grid_attributes,
        )
        plant_info = get_esolar_data(username, password, plants, use_pv_grid_attributes)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)
    except ValueError as err:
        err_str = str(err)

        if "Invalid authentication credentials" in err_str:
            raise InvalidAuth from err
        if "API rate limit exceeded." in err_str:
            raise APIRatelimitExceeded from err

        _LOGGER.exception("Unexpected exception")
        raise UnknownError from err

    else:
        if "error" in plant_info:
            raise UnknownError(plant_info["error"])

        if plant_info.get("status") != "success":
            _LOGGER.exception("Unexpected response: %s", plant_info)
            raise UnknownError
    return cast(ESolarResponse, plant_info)
