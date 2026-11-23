from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import GboError
from .const import DOMAIN
from .coordinator import GboCoordinator
from .entity import GboCoordinatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GBO-Aku buttons."""
    coordinator: GboCoordinator = entry.runtime_data
    async_add_entities([GboSyncTimeButton(coordinator, entry.entry_id)])


class GboSyncTimeButton(GboCoordinatorEntity, ButtonEntity):
    """Synchronize GBO-Aku clock."""

    _attr_translation_key = "sync_time"
    _attr_icon = "mdi:clock-sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GboCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_sync_time"

    async def async_press(self) -> None:
        """Synchronize GBO-Aku clock from Home Assistant."""
        try:
            await self.coordinator.async_sync_time()
        except GboError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="sync_time_failed",
                translation_placeholders={"error": str(err)},
            ) from err
