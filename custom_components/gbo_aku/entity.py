from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GboCoordinator


class GboCoordinatorEntity(CoordinatorEntity[GboCoordinator]):
    """Base entity for GBO-Aku data entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GboCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def available(self) -> bool:
        """Use GBO communication grace period instead of one failed poll."""
        return (
            super().available
            and self.coordinator.communication_available
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return GBO-Aku device information."""
        d = self.coordinator.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="GBO-Aku",
            manufacturer="Yorix",
            model="GBO-Aku 3PI" if d.get("type_id") == 3 else "GBO-Aku",
            sw_version=d.get("firmware"),
        )
