from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .client import GboClient
from .const import CONF_SLAVE_ID, DEFAULT_TIMEOUT
from .coordinator import GboCoordinator

PLATFORMS = [
    Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT,
    Platform.BUTTON, Platform.SWITCH,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = GboClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT],
        entry.data[CONF_SLAVE_ID], DEFAULT_TIMEOUT
    )
    coordinator = GboCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coordinator: GboCoordinator = entry.runtime_data
        await coordinator.client.close()
    return ok
