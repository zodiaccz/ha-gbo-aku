from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import GboError
from .const import DOMAIN
from .coordinator import GboCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GBO-Aku switches."""
    coordinator: GboCoordinator = entry.runtime_data
    async_add_entities(
        [GboCommunicationEnabledSwitch(coordinator, entry.entry_id)]
    )


class GboCommunicationEnabledSwitch(SwitchEntity):
    """Enable or disable Home Assistant communication with GBO-Aku."""

    _attr_has_entity_name = True
    _attr_translation_key = "communication_enabled"
    _attr_icon = "mdi:lan-connect"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GboCoordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self.entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_communication_enabled"

    @property
    def is_on(self) -> bool:
        """Return True when HA communication is enabled."""
        return not self.coordinator.client.paused

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        data = self.coordinator.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry_id)},
            name="GBO-Aku",
            manufacturer="Yorix",
            model=(
                "GBO-Aku 3PI"
                if data.get("type_id") == 3
                else "GBO-Aku"
            ),
            sw_version=data.get("firmware"),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable HA communication with GBO-Aku."""
        try:
            await self.coordinator.async_set_communication_enabled(True)
        except GboError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_enable_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable HA communication and release the PE11 connection."""
        try:
            await self.coordinator.async_set_communication_enabled(False)
        except GboError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_disable_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_write_ha_state()
