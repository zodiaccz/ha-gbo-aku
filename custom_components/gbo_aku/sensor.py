from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import GboCoordinator
from .entity import GboCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class GboSensorEntityDescription(SensorEntityDescription):
    """Describe a GBO-Aku sensor."""

    value_fn: Callable[[dict], StateType]


SENSORS = (
    GboSensorEntityDescription(
        key="current_l1",
        translation_key="current_l1",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("current_l1"),
    ),
    GboSensorEntityDescription(
        key="current_l2",
        translation_key="current_l2",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("current_l2"),
    ),
    GboSensorEntityDescription(
        key="current_l3",
        translation_key="current_l3",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("current_l3"),
    ),
    GboSensorEntityDescription(
        key="current_total",
        translation_key="current_total",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("current_sum"),
    ),
    GboSensorEntityDescription(
        key="voltage_l1",
        translation_key="voltage_l1",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("voltage_l1"),
    ),
    GboSensorEntityDescription(
        key="pi_l1",
        translation_key="pi_l1",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("pi_l1_percent"),
    ),
    GboSensorEntityDescription(
        key="pi_l2",
        translation_key="pi_l2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("pi_l2_percent"),
    ),
    GboSensorEntityDescription(
        key="pi_l3",
        translation_key="pi_l3",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("pi_l3_percent"),
    ),
    GboSensorEntityDescription(
        key="ssr1_output",
        translation_key="ssr1_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-circle-outline",
        value_fn=lambda d: d.get("ssr1_percent"),
    ),
    GboSensorEntityDescription(
        key="ssr2_output",
        translation_key="ssr2_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-circle-outline",
        value_fn=lambda d: d.get("ssr2_percent"),
    ),
    GboSensorEntityDescription(
        key="ssr3_output",
        translation_key="ssr3_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-circle-outline",
        value_fn=lambda d: d.get("ssr3_percent"),
    ),
    GboSensorEntityDescription(
        key="ssr4_output",
        translation_key="ssr4_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-circle-outline",
        value_fn=lambda d: d.get("ssr4_percent"),
    ),
    GboSensorEntityDescription(
        key="ssr5_output",
        translation_key="ssr5_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-circle-outline",
        value_fn=lambda d: d.get("ssr5_percent"),
    ),
    GboSensorEntityDescription(
        key="ssr6_output",
        translation_key="ssr6_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-circle-outline",
        value_fn=lambda d: d.get("ssr6_percent"),
    ),
    GboSensorEntityDescription(
        key="load_1_output",
        translation_key="load_1_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:radiator",
        value_fn=lambda d: d.get("load1_percent"),
    ),
    GboSensorEntityDescription(
        key="load_2_output",
        translation_key="load_2_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:radiator",
        value_fn=lambda d: d.get("load2_percent"),
    ),
    GboSensorEntityDescription(
        key="cascade_l1",
        translation_key="cascade_l1",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("cascade_l1_percent"),
    ),
    GboSensorEntityDescription(
        key="cascade_l2",
        translation_key="cascade_l2",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("cascade_l2_percent"),
    ),
    GboSensorEntityDescription(
        key="cascade_l3",
        translation_key="cascade_l3",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("cascade_l3_percent"),
    ),
    GboSensorEntityDescription(
        key="time",
        translation_key="time",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("time"),
    ),
    GboSensorEntityDescription(
        key="date",
        translation_key="date",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("date"),
    ),
    GboSensorEntityDescription(
        key="time_offset",
        translation_key="time_offset",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.get("time_offset_seconds"),
    ),
    GboSensorEntityDescription(
        key="last_time_sync",
        translation_key="last_time_sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("last_time_sync"),
    ),
    GboSensorEntityDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("firmware"),
    ),
    GboSensorEntityDescription(
        key="samples_count",
        translation_key="samples_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("samples_count"),
    ),
    GboSensorEntityDescription(
        key="pi_l1_raw",
        translation_key="pi_l1_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("pi_l1_raw"),
    ),
    GboSensorEntityDescription(
        key="pi_l2_raw",
        translation_key="pi_l2_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("pi_l2_raw"),
    ),
    GboSensorEntityDescription(
        key="pi_l3_raw",
        translation_key="pi_l3_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("pi_l3_raw"),
    ),
    GboSensorEntityDescription(
        key="relay_status_raw",
        translation_key="relay_status_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            f"0x{d['relay_status_raw']:04X}"
            if d.get("relay_status_raw") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="relays_enabled_raw",
        translation_key="relays_enabled_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            f"0x{d['relays_enabled_raw']:04X}"
            if d.get("relays_enabled_raw") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="circ_data_raw",
        translation_key="circ_data_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            f"0x{d['circ_data_raw']:04X}"
            if d.get("circ_data_raw") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="config_word_raw",
        translation_key="config_word_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            f"0x{d['config_word_raw']:04X}"
            if d.get("config_word_raw") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="ssr_enable_mask",
        translation_key="ssr_enable_mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            f"0x{d['ssr_enable_raw'] & 0x3F:02X}"
            if d.get("ssr_enable_raw") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="relay_surplus_mask",
        translation_key="relay_surplus_mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            f"0x{int(d['relay_surplus_mask']):02X}"
            if d.get("relay_surplus_mask") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="relay_nt_timer_mask",
        translation_key="relay_nt_timer_mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            f"0x{int(d['relay_nt_timer_mask']):02X}"
            if d.get("relay_nt_timer_mask") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="ssr_nt_timer_mask",
        translation_key="ssr_nt_timer_mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            f"0x{int(d['ssr_nt_timer_mask']):02X}"
            if d.get("ssr_nt_timer_mask") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="regulation_start_delay",
        translation_key="regulation_start_delay",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.get("regulation_start_delay"),
    ),
    GboSensorEntityDescription(
        key="eeprom_checksum",
        translation_key="eeprom_checksum",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            f"0x{d['eeprom_checksum']:04X}"
            if d.get("eeprom_checksum") is not None
            else None
        ),
    ),
    GboSensorEntityDescription(
        key="live_poll_interval",
        translation_key="live_poll_interval",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.get("live_poll_interval"),
    ),
    GboSensorEntityDescription(
        key="ram_poll_interval",
        translation_key="ram_poll_interval",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.get("ram_poll_interval"),
    ),
    GboSensorEntityDescription(
        key="eeprom_poll_interval",
        translation_key="eeprom_poll_interval",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.get("eeprom_poll_interval"),
    ),
    GboSensorEntityDescription(
        key="time_sync_check_interval",
        translation_key="time_sync_check_interval",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        native_unit_of_measurement="min",
        value_fn=lambda d: d.get("time_sync_check_interval"),
    ),
    GboSensorEntityDescription(
        key="max_time_offset",
        translation_key="max_time_offset",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.get("max_time_offset"),
    ),
    GboSensorEntityDescription(
        key="last_eeprom_write",
        translation_key="last_eeprom_write",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:memory-arrow-down",
        value_fn=lambda d: d.get("last_eeprom_write"),
    ),
    GboSensorEntityDescription(
        key="eeprom_writes_by_ha",
        translation_key="eeprom_writes_by_ha",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:counter",
        value_fn=lambda d: d.get("eeprom_writes_by_ha", 0),
    ),
    GboSensorEntityDescription(
        key="last_flash_backup",
        translation_key="last_flash_backup",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:memory-arrow-up",
        value_fn=lambda d: d.get("last_flash_backup"),
    ),
    GboSensorEntityDescription(
        key="flash_backups_by_ha",
        translation_key="flash_backups_by_ha",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:counter",
        value_fn=lambda d: d.get("flash_backups_by_ha", 0),
    ),
    GboSensorEntityDescription(
        key="communication_status",
        translation_key="communication_status",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:lan",
        value_fn=lambda d: d.get("communication_status"),
    ),
    GboSensorEntityDescription(
        key="consecutive_failures",
        translation_key="consecutive_failures",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:counter",
        value_fn=lambda d: d.get("consecutive_failures"),
    ),
    GboSensorEntityDescription(
        key="last_successful_communication",
        translation_key="last_successful_communication",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:check-network-outline",
        value_fn=lambda d: d.get("last_successful_communication"),
    ),
    GboSensorEntityDescription(
        key="last_communication_error",
        translation_key="last_communication_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:network-off-outline",
        value_fn=lambda d: d.get("last_communication_error"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GBO-Aku sensors."""
    coordinator: GboCoordinator = entry.runtime_data
    async_add_entities(
        GboSensor(coordinator, entry.entry_id, description)
        for description in SENSORS
    )


class GboSensor(GboCoordinatorEntity, SensorEntity):
    """GBO-Aku sensor."""

    entity_description: GboSensorEntityDescription

    def __init__(
        self,
        coordinator: GboCoordinator,
        entry_id: str,
        description: GboSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

        if description.key == "communication_status":
            self._attr_options = [
                "connected",
                "degraded",
                "unavailable",
            ]

    @property
    def available(self) -> bool:
        """Keep communication diagnostics readable during an outage."""
        if self.entity_description.key in {
            "communication_status",
            "consecutive_failures",
            "last_successful_communication",
            "last_communication_error",
        }:
            return True
        return super().available

    @property
    def native_value(self) -> StateType:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.coordinator.data or {})
