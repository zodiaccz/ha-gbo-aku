from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers import selector

from .client import GboClient, GboError
from .const import (
    CONF_AUTO_TIME_SYNC,
    CONF_EEPROM_POLL_INTERVAL,
    CONF_LIVE_POLL_INTERVAL,
    CONF_MAX_TIME_OFFSET,
    CONF_RAM_POLL_INTERVAL,
    CONF_RETRY_FAILED_REQUEST,
    CONF_SLAVE_ID,
    CONF_TIME_SYNC_CHECK_INTERVAL,
    CONF_UNAVAILABLE_AFTER,
    DEFAULT_AUTO_TIME_SYNC,
    DEFAULT_EEPROM_POLL_INTERVAL,
    DEFAULT_LIVE_POLL_INTERVAL,
    DEFAULT_MAX_TIME_OFFSET,
    DEFAULT_PORT,
    DEFAULT_RAM_POLL_INTERVAL,
    DEFAULT_RETRY_FAILED_REQUEST,
    DEFAULT_SLAVE_ID,
    DEFAULT_TIME_SYNC_CHECK_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_UNAVAILABLE_AFTER,
    DOMAIN,
    MAX_EEPROM_POLL_INTERVAL,
    MAX_LIVE_POLL_INTERVAL,
    MAX_MAX_TIME_OFFSET,
    MAX_RAM_POLL_INTERVAL,
    MAX_RETRY_FAILED_REQUEST,
    MAX_TIME_SYNC_CHECK_INTERVAL,
    MAX_UNAVAILABLE_AFTER,
    MIN_EEPROM_POLL_INTERVAL,
    MIN_LIVE_POLL_INTERVAL,
    MIN_MAX_TIME_OFFSET,
    MIN_RAM_POLL_INTERVAL,
    MIN_RETRY_FAILED_REQUEST,
    MIN_TIME_SYNC_CHECK_INTERVAL,
    MIN_UNAVAILABLE_AFTER,
)
from .coordinator import GboCoordinator


class GboAkuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for GBO-Aku."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "GboAkuOptionsFlow":
        return GboAkuOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Configure PE11 / Modbus connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            slave = int(user_input[CONF_SLAVE_ID])

            for entry in self._async_current_entries():
                if (
                    entry.data.get(CONF_HOST),
                    entry.data.get(CONF_PORT),
                    entry.data.get(CONF_SLAVE_ID),
                ) == (host, port, slave):
                    return self.async_abort(reason="already_configured")

            if not host:
                errors[CONF_HOST] = "invalid_host"
            else:
                client = GboClient(host, port, slave, DEFAULT_TIMEOUT)
                try:
                    await client.read_holding_registers(34, 1)
                except GboError:
                    errors["base"] = "cannot_connect"
                finally:
                    await client.close()

            if not errors:
                return self.async_create_entry(
                    title="GBO-Aku",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_SLAVE_ID: slave,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(
                        CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=247,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )


class GboAkuOptionsFlow(OptionsFlowWithReload):
    """Runtime options and explicit verified EEPROM configuration."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "runtime_settings",
                "eeprom_surplus_outputs",
                "eeprom_nt_timer_outputs",
                "eeprom_regulation",
                "flash_backup",
            ],
        )

    @property
    def _coordinator(self) -> GboCoordinator:
        return self.config_entry.runtime_data

    async def _load_eeprom_data(self) -> dict:
        """Populate the form from a fresh controller read."""
        try:
            return await self._coordinator.async_refresh_eeprom()
        except GboError as err:
            raise AbortFlow("eeprom_read_failed") from err

    async def _apply_eeprom(
        self,
        user_input: dict[str, Any],
    ) -> tuple[bool, dict[str, str]]:
        try:
            await self._coordinator.async_write_verified_eeprom(user_input)
        except (GboError, ValueError):
            return False, {"base": "eeprom_write_failed"}
        return True, {}

    async def async_step_flash_backup(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Explicitly copy the current EEPROM configuration to MCU FLASH."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not bool(user_input.get("confirm_flash_backup", False)):
                errors["base"] = "flash_backup_not_confirmed"
            else:
                try:
                    await self._coordinator.async_backup_eeprom_to_flash()
                except GboError:
                    errors["base"] = "flash_backup_failed"
                else:
                    # The coordinator already reconnected after the GBO reset.
                    return self.async_create_entry(
                        data=dict(self.config_entry.options)
                    )

        return self.async_show_form(
            step_id="flash_backup",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "confirm_flash_backup",
                        default=False,
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_runtime_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Configure polling, resilience and clock synchronization."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        return self.async_show_form(
            step_id="runtime_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LIVE_POLL_INTERVAL,
                        default=current.get(
                            CONF_LIVE_POLL_INTERVAL, DEFAULT_LIVE_POLL_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_LIVE_POLL_INTERVAL,
                            max=MAX_LIVE_POLL_INTERVAL,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_RAM_POLL_INTERVAL,
                        default=current.get(
                            CONF_RAM_POLL_INTERVAL, DEFAULT_RAM_POLL_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_RAM_POLL_INTERVAL,
                            max=MAX_RAM_POLL_INTERVAL,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_EEPROM_POLL_INTERVAL,
                        default=current.get(
                            CONF_EEPROM_POLL_INTERVAL, DEFAULT_EEPROM_POLL_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_EEPROM_POLL_INTERVAL,
                            max=MAX_EEPROM_POLL_INTERVAL,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_RETRY_FAILED_REQUEST,
                        default=current.get(
                            CONF_RETRY_FAILED_REQUEST, DEFAULT_RETRY_FAILED_REQUEST
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_RETRY_FAILED_REQUEST,
                            max=MAX_RETRY_FAILED_REQUEST,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_UNAVAILABLE_AFTER,
                        default=current.get(
                            CONF_UNAVAILABLE_AFTER, DEFAULT_UNAVAILABLE_AFTER
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_UNAVAILABLE_AFTER,
                            max=MAX_UNAVAILABLE_AFTER,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_AUTO_TIME_SYNC,
                        default=current.get(
                            CONF_AUTO_TIME_SYNC, DEFAULT_AUTO_TIME_SYNC
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_TIME_SYNC_CHECK_INTERVAL,
                        default=current.get(
                            CONF_TIME_SYNC_CHECK_INTERVAL,
                            DEFAULT_TIME_SYNC_CHECK_INTERVAL,
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_TIME_SYNC_CHECK_INTERVAL,
                            max=MAX_TIME_SYNC_CHECK_INTERVAL,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Required(
                        CONF_MAX_TIME_OFFSET,
                        default=current.get(
                            CONF_MAX_TIME_OFFSET, DEFAULT_MAX_TIME_OFFSET
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_MAX_TIME_OFFSET,
                            max=MAX_MAX_TIME_OFFSET,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )

    async def async_step_eeprom_surplus_outputs(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Configure black links: outputs participating in surplus regulation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            ok, errors = await self._apply_eeprom(user_input)
            if ok:
                return self.async_create_entry(data=dict(self.config_entry.options))

        data = await self._load_eeprom_data()

        schema: dict[Any, Any] = {}
        for number in range(1, 6):
            key = f"relay_k{number}_surplus_enabled"
            schema[vol.Required(key, default=bool(data.get(key, False)))] = (
                selector.BooleanSelector()
            )
        for number in range(1, 7):
            key = f"ssr{number}_surplus_enabled"
            schema[vol.Required(key, default=bool(data.get(key, False)))] = (
                selector.BooleanSelector()
            )

        return self.async_show_form(
            step_id="eeprom_surplus_outputs",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_eeprom_nt_timer_outputs(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Configure red links: outputs enabled by NT/timer logic."""
        errors: dict[str, str] = {}
        if user_input is not None:
            ok, errors = await self._apply_eeprom(user_input)
            if ok:
                return self.async_create_entry(data=dict(self.config_entry.options))

        data = await self._load_eeprom_data()

        schema: dict[Any, Any] = {}
        for number in range(1, 6):
            key = f"relay_k{number}_nt_timer_enabled"
            schema[vol.Required(key, default=bool(data.get(key, False)))] = (
                selector.BooleanSelector()
            )
        for number in range(1, 7):
            key = f"ssr{number}_nt_timer_enabled"
            schema[vol.Required(key, default=bool(data.get(key, False)))] = (
                selector.BooleanSelector()
            )

        return self.async_show_form(
            step_id="eeprom_nt_timer_outputs",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_eeprom_regulation(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Configure verified regulation/clock EEPROM flags."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = dict(user_input)
            user_input["regulation_start_delay"] = int(
                user_input["regulation_start_delay"]
            )
            ok, errors = await self._apply_eeprom(user_input)
            if ok:
                return self.async_create_entry(data=dict(self.config_entry.options))

        data = await self._load_eeprom_data()

        return self.async_show_form(
            step_id="eeprom_regulation",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "nt_bypass_enabled",
                        default=bool(data.get("nt_bypass_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "ssr_slow_modulation_enabled",
                        default=bool(data.get("ssr_slow_modulation_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "udc_control_enabled",
                        default=bool(data.get("udc_control_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "udc_control_inverted",
                        default=bool(data.get("udc_control_inverted", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "half_period_modulation_enabled",
                        default=bool(data.get("half_period_modulation_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "automatic_dst_enabled",
                        default=bool(data.get("automatic_dst_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "stop_after_dark_enabled",
                        default=bool(data.get("stop_after_dark_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "regulation_start_delay",
                        default=int(data.get("regulation_start_delay", 1)),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=255,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        "k5_mode",
                        default=str(data.get("k5_mode", "cascade")),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["cascade", "timer_only", "surplus_pump", "unknown"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="k5_mode",
                        )
                    ),
                    vol.Required(
                        "night_monday_enabled",
                        default=bool(data.get("night_monday_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "night_tuesday_enabled",
                        default=bool(data.get("night_tuesday_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "night_wednesday_enabled",
                        default=bool(data.get("night_wednesday_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "night_thursday_enabled",
                        default=bool(data.get("night_thursday_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "night_friday_enabled",
                        default=bool(data.get("night_friday_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "night_saturday_enabled",
                        default=bool(data.get("night_saturday_enabled", False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "night_sunday_enabled",
                        default=bool(data.get("night_sunday_enabled", False)),
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors,
        )
