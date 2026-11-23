from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import GboCoordinator
from .entity import GboCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class GboBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a GBO-Aku binary sensor."""

    value_fn: Callable[[dict], bool | None]


_binary: list[GboBinarySensorEntityDescription] = [
    GboBinarySensorEntityDescription(
        key="low_tariff",
        translation_key="low_tariff",
        icon="mdi:transmission-tower",
        value_fn=lambda d: d.get("low_tariff"),
    ),
]

# Preserve v0.5 unique IDs/entity keys, but correct their semantics and bit map:
# these are the BLACK/surplus-regulation links.
for number in range(1, 7):
    _binary.append(
        GboBinarySensorEntityDescription(
            key=f"ssr{number}_enabled",
            translation_key=f"ssr{number}_enabled",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d, n=number: d.get(f"ssr{n}_surplus_enabled"),
        )
    )

for number in range(1, 6):
    _binary.append(
        GboBinarySensorEntityDescription(
            key=f"relay_k{number}_enabled",
            translation_key=f"relay_k{number}_enabled",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d, n=number: d.get(f"relay_k{n}_surplus_enabled"),
        )
    )

# New precise RED/NT+timer link diagnostics.
for number in range(1, 7):
    _binary.append(
        GboBinarySensorEntityDescription(
            key=f"ssr{number}_nt_timer_enabled",
            translation_key=f"ssr{number}_nt_timer_enabled",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=lambda d, n=number: d.get(f"ssr{n}_nt_timer_enabled"),
        )
    )

for number in range(1, 6):
    _binary.append(
        GboBinarySensorEntityDescription(
            key=f"relay_k{number}_nt_timer_enabled",
            translation_key=f"relay_k{number}_nt_timer_enabled",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=lambda d, n=number: d.get(f"relay_k{n}_nt_timer_enabled"),
        )
    )

_binary.append(
    GboBinarySensorEntityDescription(
        key="time_is_set",
        translation_key="time_is_set",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("time_is_set"),
    )
)

BINARY_SENSORS = tuple(_binary)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GBO-Aku binary sensors."""
    coordinator: GboCoordinator = entry.runtime_data
    async_add_entities(
        GboBinarySensor(coordinator, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class GboBinarySensor(GboCoordinatorEntity, BinarySensorEntity):
    """GBO-Aku binary sensor."""

    entity_description: GboBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: GboCoordinator,
        entry_id: str,
        description: GboBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the binary state."""
        return self.entity_description.value_fn(self.coordinator.data or {})
