from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import GboError
from .const import DOMAIN, MODE_TO_VALUE
from .coordinator import GboCoordinator
from .entity import GboCoordinatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GBO-Aku select entities."""
    coordinator: GboCoordinator = entry.runtime_data
    async_add_entities([GboModeSelect(coordinator, entry.entry_id)])


class GboModeSelect(GboCoordinatorEntity, SelectEntity):
    """GBO-Aku external control mode."""

    _attr_translation_key = "mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(MODE_TO_VALUE)

    def __init__(self, coordinator: GboCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_mode"

    @property
    def current_option(self) -> str | None:
        """Return current stable mode key."""
        return (self.coordinator.data or {}).get("mode")

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return raw ExternControl value."""
        value = (self.coordinator.data or {}).get("extern_control_raw")
        return {
            "raw_value": f"0x{value:04X}" if value is not None else None
        }

    async def async_select_option(self, option: str) -> None:
        """Set GBO-Aku external control mode."""
        try:
            await self.coordinator.async_set_mode(option)
        except (GboError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_mode_failed",
                translation_placeholders={"error": str(err)},
            ) from err
