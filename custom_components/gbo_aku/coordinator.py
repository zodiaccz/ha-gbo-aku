from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import logging
import time
from typing import TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .cascade import raw_to_percent, split_two_stage
from .client import GboClient, GboError
from .eeprom import (
    ADDR_CHECKSUM,
    ADDR_CONFIG_WORD,
    EEPROM_COMMIT_VALUE,
    build_verified_updates,
    decode_verified_config,
    ssr_mask,
)
from .const import (
    CONF_AUTO_TIME_SYNC,
    CONF_EEPROM_POLL_INTERVAL,
    CONF_LIVE_POLL_INTERVAL,
    CONF_MAX_TIME_OFFSET,
    CONF_RAM_POLL_INTERVAL,
    CONF_RETRY_FAILED_REQUEST,
    CONF_TIME_SYNC_CHECK_INTERVAL,
    CONF_UNAVAILABLE_AFTER,
    DEFAULT_AUTO_TIME_SYNC,
    DEFAULT_EEPROM_POLL_INTERVAL,
    DEFAULT_LIVE_POLL_INTERVAL,
    DEFAULT_MAX_TIME_OFFSET,
    DEFAULT_RAM_POLL_INTERVAL,
    DEFAULT_RETRY_FAILED_REQUEST,
    DEFAULT_TIME_SYNC_CHECK_INTERVAL,
    DEFAULT_UNAVAILABLE_AFTER,
    DOMAIN,
    EEPROM_COUNT,
    EEPROM_START,
    LIVE_COUNT,
    LIVE_START,
    MODE_ALL_OFF,
    MODE_ALL_ON,
    MODE_TO_VALUE,
    RAM_COUNT,
    RAM_START,
    VALUE_TO_MODE,
)

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


def _s16(value: int) -> int:
    """Convert unsigned 16-bit word to signed int16."""
    return value - 0x10000 if value & 0x8000 else value


def _word_at(
    registers: list[int],
    start_address: int,
    address: int,
) -> int:
    """Get one GBO word using vendor byte-oriented PDU addressing."""
    offset = address - start_address
    if offset < 0 or offset % 2:
        raise ValueError(f"Invalid GBO byte address {address}")
    return registers[offset // 2]


class GboCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate GBO-Aku polling, diagnostics and clock synchronization."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GboClient,
    ) -> None:
        self.live_interval = int(
            entry.options.get(
                CONF_LIVE_POLL_INTERVAL,
                DEFAULT_LIVE_POLL_INTERVAL,
            )
        )
        self.ram_interval = int(
            entry.options.get(
                CONF_RAM_POLL_INTERVAL,
                DEFAULT_RAM_POLL_INTERVAL,
            )
        )
        self.eeprom_interval = int(
            entry.options.get(
                CONF_EEPROM_POLL_INTERVAL,
                DEFAULT_EEPROM_POLL_INTERVAL,
            )
        )

        self.auto_time_sync = bool(
            entry.options.get(
                CONF_AUTO_TIME_SYNC,
                DEFAULT_AUTO_TIME_SYNC,
            )
        )
        self.time_sync_check_interval = int(
            entry.options.get(
                CONF_TIME_SYNC_CHECK_INTERVAL,
                DEFAULT_TIME_SYNC_CHECK_INTERVAL,
            )
        )
        self.max_time_offset = int(
            entry.options.get(
                CONF_MAX_TIME_OFFSET,
                DEFAULT_MAX_TIME_OFFSET,
            )
        )

        self.retry_failed_request = int(
            entry.options.get(
                CONF_RETRY_FAILED_REQUEST,
                DEFAULT_RETRY_FAILED_REQUEST,
            )
        )
        self.unavailable_after = int(
            entry.options.get(
                CONF_UNAVAILABLE_AFTER,
                DEFAULT_UNAVAILABLE_AFTER,
            )
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.live_interval),
        )

        self.client = client

        self._last_ram = 0.0
        self._last_eeprom = 0.0
        self._last_time_check = 0.0

        # Communication-health state.
        self._last_live_success_mono: float | None = None
        self._last_successful_communication: datetime | None = None
        self._last_communication_error: str | None = None
        self._consecutive_failures = 0
        self._cycle_had_error = False
        self._last_eeprom_write: datetime | None = None
        self._eeprom_write_count = 0
        self._last_flash_backup: datetime | None = None
        self._flash_backup_count = 0

    @property
    def communication_available(self) -> bool:
        """Whether normal GBO entities should currently be available."""
        if self.client.paused:
            return False

        if self._last_live_success_mono is None:
            return False

        return (
            time.monotonic() - self._last_live_success_mono
            <= self.unavailable_after
        )

    @property
    def communication_status(self) -> str:
        """Return stable communication status key."""
        if self.client.paused:
            return "unavailable"

        if not self.communication_available:
            return "unavailable"

        if self._consecutive_failures > 0:
            return "degraded"

        return "connected"

    def mark_ram_stale(self) -> None:
        """Force RAM refresh during the next coordinator update."""
        self._last_ram = 0.0

    def mark_eeprom_stale(self) -> None:
        """Force EEPROM refresh during the next coordinator update."""
        self._last_eeprom = 0.0

    def mark_all_stale(self) -> None:
        """Force all slower blocks to refresh."""
        self.mark_ram_stale()
        self.mark_eeprom_stale()

    def _time_check_due(
        self,
        data: dict,
        now_mono: float,
    ) -> bool:
        """Return whether an automatic clock check requires a RAM read."""
        if not self.auto_time_sync:
            return False

        if data.get("time_is_set") is False:
            return True

        if self._last_time_check == 0.0:
            return True

        return (
            now_mono - self._last_time_check
            >= self.time_sync_check_interval * 60
        )

    @staticmethod
    def _format_error(block: str, err: Exception) -> str:
        """Create a compact diagnostic error string."""
        detail = str(err).strip() or err.__class__.__name__
        return f"{block}: {detail}"

    async def _request_with_retry(
        self,
        block: str,
        operation: Callable[[], Awaitable[_T]],
    ) -> tuple[_T | None, GboError | None]:
        """Run one read operation with reconnect and configured retries."""
        last_error: GboError | None = None
        total_attempts = 1 + self.retry_failed_request

        for attempt in range(total_attempts):
            try:
                result = await operation()
                return result, None
            except GboError as err:
                last_error = err
                await self.client.close()

                if attempt < total_attempts - 1:
                    # Let TCP/PE11/L2TP settle briefly before reconnect.
                    await asyncio.sleep(0.10)

        if last_error is not None:
            _LOGGER.warning(
                "GBO-Aku %s read failed after %s attempt(s): %s",
                block,
                total_attempts,
                last_error,
            )
        return None, last_error

    def _record_block_failure(
        self,
        block: str,
        err: Exception,
    ) -> None:
        """Record a failed block without dropping cached values."""
        self._cycle_had_error = True
        self._last_communication_error = self._format_error(block, err)

    def _record_live_success(self, now_mono: float) -> None:
        """Record live FC04 as the availability heartbeat."""
        self._last_live_success_mono = now_mono
        self._last_successful_communication = dt_util.now()

    def _update_health_data(self, data: dict) -> None:
        """Expose current communication health in coordinator data."""
        if self._cycle_had_error:
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0

        data.update(
            {
                "communication_status": self.communication_status,
                "consecutive_failures": self._consecutive_failures,
                "last_successful_communication":
                    self._last_successful_communication,
                "last_communication_error":
                    self._last_communication_error,
                "last_eeprom_write": self._last_eeprom_write,
                "eeprom_writes_by_ha": self._eeprom_write_count,
                "last_flash_backup": self._last_flash_backup,
                "flash_backups_by_ha": self._flash_backup_count,
                "retry_failed_request": self.retry_failed_request,
                "unavailable_after": self.unavailable_after,
            }
        )

    async def _async_update_data(self) -> dict:
        """Poll live, RAM and EEPROM independently and keep last good data."""
        data = dict(self.data or {})

        data.update(
            {
                "live_poll_interval": self.live_interval,
                "ram_poll_interval": self.ram_interval,
                "eeprom_poll_interval": self.eeprom_interval,
                "auto_time_sync": self.auto_time_sync,
                "time_sync_check_interval":
                    self.time_sync_check_interval,
                "max_time_offset": self.max_time_offset,
                "retry_failed_request": self.retry_failed_request,
                "unavailable_after": self.unavailable_after,
            }
        )

        self._cycle_had_error = False

        if self.client.paused:
            self._update_health_data(data)
            return data

        now_mono = time.monotonic()

        # ------------------------------------------------------------------
        # LIVE FC04
        # This is the heartbeat for overall entity availability.
        # ------------------------------------------------------------------
        live, live_err = await self._request_with_retry(
            "live",
            lambda: self.client.read_input_registers(
                LIVE_START,
                LIVE_COUNT,
            ),
        )
        if live_err is None and live is not None:
            data.update(self._decode_live(live))
            self._record_live_success(now_mono)
        else:
            self._record_block_failure(
                "live",
                live_err or GboError("unknown live read error"),
            )

        # ------------------------------------------------------------------
        # RAM FC03
        # Failure leaves previous RAM values intact and retries next cycle.
        # ------------------------------------------------------------------
        ram_due = (
            not self.data
            or now_mono - self._last_ram >= self.ram_interval
        )
        time_check_due = self._time_check_due(data, now_mono)

        if ram_due or time_check_due:
            ram, ram_err = await self._request_with_retry(
                "ram",
                lambda: self.client.read_holding_registers(
                    RAM_START,
                    RAM_COUNT,
                ),
            )
            if ram_err is None and ram is not None:
                data.update(self._decode_ram(ram))
                self._last_ram = now_mono

                if self.auto_time_sync and (
                    time_check_due
                    or data.get("time_is_set") is False
                ):
                    try:
                        await self._maybe_auto_sync_time(
                            data,
                            now_mono,
                        )
                    except GboError as err:
                        self._record_block_failure("time_sync", err)
                        self.mark_ram_stale()
            else:
                self._record_block_failure(
                    "ram",
                    ram_err or GboError("unknown RAM read error"),
                )
                self.mark_ram_stale()

        # ------------------------------------------------------------------
        # EEPROM FC03
        # Failure leaves previous EEPROM values intact and retries next cycle.
        # ------------------------------------------------------------------
        eeprom_due = (
            not self.data
            or now_mono - self._last_eeprom >= self.eeprom_interval
        )

        if eeprom_due:
            eeprom, eeprom_err = await self._request_with_retry(
                "eeprom",
                lambda: self.client.read_holding_registers(
                    EEPROM_START,
                    EEPROM_COUNT,
                ),
            )
            if eeprom_err is None and eeprom is not None:
                data.update(self._decode_eeprom(eeprom))
                self._last_eeprom = now_mono
            else:
                self._record_block_failure(
                    "eeprom",
                    eeprom_err or GboError("unknown EEPROM read error"),
                )
                self.mark_eeprom_stale()

        self._update_cascade_values(data)
        self._update_health_data(data)
        return data

    @staticmethod
    def _decode_live(registers: list[int]) -> dict:
        """Decode FC04 live block."""
        pi_l1_word = _word_at(registers, LIVE_START, 18)
        pi_l2_word = _word_at(registers, LIVE_START, 36)
        pi_l3_word = _word_at(registers, LIVE_START, 52)

        pi_l1_raw = pi_l1_word & 0xFF
        pi_l2_raw = pi_l2_word & 0xFF
        pi_l3_raw = pi_l3_word & 0xFF

        return {
            "current_l1": _s16(
                _word_at(registers, LIVE_START, 8)
            ) / 10.0,
            "current_l2": _s16(
                _word_at(registers, LIVE_START, 10)
            ) / 10.0,
            "current_l3": _s16(
                _word_at(registers, LIVE_START, 12)
            ) / 10.0,
            "current_sum": _s16(
                _word_at(registers, LIVE_START, 14)
            ) / 10.0,
            "voltage_l1": _word_at(
                registers,
                LIVE_START,
                16,
            ),
            "pi_l1_raw": pi_l1_raw,
            "pi_l2_raw": pi_l2_raw,
            "pi_l3_raw": pi_l3_raw,
            "pi_l1_percent": raw_to_percent(pi_l1_raw),
            "pi_l2_percent": raw_to_percent(pi_l2_raw),
            "pi_l3_percent": raw_to_percent(pi_l3_raw),
            "samples_count": (pi_l1_word >> 8) & 0xFF,
            "circ_data_raw": _word_at(
                registers,
                LIVE_START,
                24,
            ),
        }

    @staticmethod
    def _decode_ram(registers: list[int]) -> dict:
        """Decode FC03 runtime RAM block."""
        time_word = _word_at(registers, RAM_START, 0)
        hour_dow_word = _word_at(registers, RAM_START, 2)
        rtc_word = _word_at(registers, RAM_START, 4)
        date_word = _word_at(registers, RAM_START, 6)
        year_word = _word_at(registers, RAM_START, 8)
        extern_control = _word_at(registers, RAM_START, 14)
        extend_action = _word_at(registers, RAM_START, 16)

        second = time_word & 0xFF
        minute = (time_word >> 8) & 0xFF
        hour = hour_dow_word & 0xFF
        day_of_week = (hour_dow_word >> 8) & 0xFF
        day = date_word & 0xFF
        month = (date_word >> 8) & 0xFF
        year = 2000 + year_word

        relay_status = _word_at(registers, RAM_START, 10)

        return {
            "time": f"{hour:02d}:{minute:02d}:{second:02d}",
            "date": f"{day:02d}.{month:02d}.{year:04d}",
            "gbo_second": second,
            "gbo_minute": minute,
            "gbo_hour": hour,
            "gbo_day": day,
            "gbo_month": month,
            "gbo_year": year,
            "day_of_week": day_of_week,
            "rtc_cfg": (rtc_word >> 8) & 0xFF,
            "time_is_set": (rtc_word & 0xFF) == 0x55,
            "relay_status_raw": relay_status,
            "low_tariff": bool(relay_status & 0x0100),
            "time_corr_cnt": _word_at(
                registers,
                RAM_START,
                12,
            ),
            "extern_control_raw": extern_control,
            "mode": VALUE_TO_MODE.get(extern_control),
            "extend_action_level": extend_action & 0xFF,
            "extend_pi_copy": (extend_action >> 8) & 0xFF,
        }

    @staticmethod
    def _decode_eeprom(registers: list[int]) -> dict:
        """Decode EEPROM values, including empirically verified configuration."""
        config_word = _word_at(registers, EEPROM_START, 20)
        firmware_raw = _word_at(registers, EEPROM_START, 34)
        relays_enabled = _word_at(registers, EEPROM_START, 60)
        ssr_enable = _word_at(registers, EEPROM_START, 64)
        flags_word = _word_at(registers, EEPROM_START, 74)
        weekly_schedule = _word_at(registers, EEPROM_START, 86)
        boot_type_word = _word_at(registers, EEPROM_START, 70)

        decoded = decode_verified_config(
            config_word,
            relays_enabled,
            ssr_enable,
            flags_word,
            weekly_schedule,
        )
        decoded.update(
            {
                "config_word_raw": config_word,
                "firmware_raw": firmware_raw,
                "firmware": (
                    f"{firmware_raw // 1000}."
                    f"{firmware_raw % 1000:03d}"
                ),
                "relays_enabled_raw": relays_enabled,
                "ssr_enable_raw": ssr_enable,
                "flags_word_raw": flags_word,
                "weekly_schedule_raw": weekly_schedule,
                "eeprom_checksum": _word_at(
                    registers,
                    EEPROM_START,
                    76,
                ),
                "type_id": (boot_type_word >> 8) & 0xFF,
            }
        )
        return decoded

    @staticmethod
    def _update_cascade_values(data: dict) -> None:
        """Calculate effective outputs of SSR1..SSR6."""
        mask = int(data.get("ssr_enable_raw", 0x003F)) & 0x3F
        extern_control = int(
            data.get("extern_control_raw", 0)
        )

        def enabled(ssr_number: int) -> bool:
            return bool(mask & ssr_mask(ssr_number))

        pi_l1_raw = int(data.get("pi_l1_raw", 0))
        pi_l2_raw = int(data.get("pi_l2_raw", 0))
        pi_l3_raw = int(data.get("pi_l3_raw", 0))

        if extern_control == MODE_ALL_ON:
            ssr1 = 100.0 if enabled(1) else 0.0
            ssr2 = 100.0 if enabled(2) else 0.0
            ssr3 = 100.0 if enabled(3) else 0.0
            ssr4 = 100.0 if enabled(4) else 0.0
            ssr5 = 100.0 if enabled(5) else 0.0
            ssr6 = 100.0 if enabled(6) else 0.0

        elif extern_control == MODE_ALL_OFF:
            ssr1 = ssr2 = ssr3 = 0.0
            ssr4 = ssr5 = ssr6 = 0.0

        else:
            ssr1, ssr4 = split_two_stage(
                pi_l1_raw,
                enabled(1),
                enabled(4),
            )
            ssr2, ssr5 = split_two_stage(
                pi_l2_raw,
                enabled(2),
                enabled(5),
            )
            ssr3, ssr6 = split_two_stage(
                pi_l3_raw,
                enabled(3),
                enabled(6),
            )

        data.update(
            {
                "ssr1_percent": ssr1,
                "ssr2_percent": ssr2,
                "ssr3_percent": ssr3,
                "ssr4_percent": ssr4,
                "ssr5_percent": ssr5,
                "ssr6_percent": ssr6,
                "cascade_l1_percent": round(ssr1 + ssr4, 1),
                "cascade_l2_percent": round(ssr2 + ssr5, 1),
                "cascade_l3_percent": round(ssr3 + ssr6, 1),
                "load1_percent": round(
                    (ssr1 + ssr2 + ssr3) / 3.0,
                    1,
                ),
                "load2_percent": round(
                    (ssr4 + ssr5 + ssr6) / 3.0,
                    1,
                ),
            }
        )

    @staticmethod
    def _gbo_datetime(
        data: dict,
        reference: datetime,
    ) -> datetime | None:
        """Build timezone-aware GBO datetime from decoded RAM fields."""
        try:
            return reference.replace(
                year=int(data["gbo_year"]),
                month=int(data["gbo_month"]),
                day=int(data["gbo_day"]),
                hour=int(data["gbo_hour"]),
                minute=int(data["gbo_minute"]),
                second=int(data["gbo_second"]),
                microsecond=0,
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _apply_clock_to_data(
        data: dict,
        value: datetime,
    ) -> None:
        """Update cached clock fields after a successful RAM time write."""
        data.update(
            {
                "time": value.strftime("%H:%M:%S"),
                "date": value.strftime("%d.%m.%Y"),
                "gbo_second": value.second,
                "gbo_minute": value.minute,
                "gbo_hour": value.hour,
                "gbo_day": value.day,
                "gbo_month": value.month,
                "gbo_year": value.year,
                "day_of_week": value.isoweekday() % 7,
                "time_is_set": True,
            }
        )

    async def _write_current_time(
        self,
        rtc_cfg: int,
        now: datetime | None = None,
    ) -> datetime:
        """Write current HA local time to GBO RAM via FC16."""
        if self.client.paused:
            raise GboError("GBO-Aku communication is disabled")

        current = now or dt_util.now()
        day_of_week = current.isoweekday() % 7

        values = [
            (current.minute << 8) | current.second,
            (day_of_week << 8) | current.hour,
            ((int(rtc_cfg) & 0xFF) << 8) | 0x55,
            (current.month << 8) | current.day,
            current.year - 2000,
        ]

        await self.client.write_multiple_registers(
            0,
            values,
        )
        return current

    async def _maybe_auto_sync_time(
        self,
        data: dict,
        now_mono: float,
    ) -> None:
        """Check clock drift and synchronize only when necessary."""
        self._last_time_check = now_mono

        now = dt_util.now().replace(microsecond=0)
        gbo_time = self._gbo_datetime(
            data,
            now,
        )

        if gbo_time is None:
            offset_seconds: int | None = None
        else:
            offset_seconds = int(
                round((gbo_time - now).total_seconds())
            )

        data["time_offset_seconds"] = offset_seconds

        must_sync = (
            not bool(data.get("time_is_set"))
            or gbo_time is None
            or (
                offset_seconds is not None
                and abs(offset_seconds) > self.max_time_offset
            )
        )

        if not must_sync:
            return

        rtc_cfg = int(data.get("rtc_cfg", 0x0E)) & 0xFF
        written_at = await self._write_current_time(
            rtc_cfg,
            now,
        )

        self._apply_clock_to_data(
            data,
            written_at,
        )
        data["time_offset_seconds"] = 0
        data["last_time_sync"] = written_at.isoformat()

        self.mark_ram_stale()

        _LOGGER.info(
            "GBO-Aku clock synchronized (previous offset: %s s)",
            offset_seconds,
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set ExternControl in RAM using FC16."""
        if mode not in MODE_TO_VALUE:
            raise ValueError(mode)

        await self.client.write_multiple_registers(
            14,
            [MODE_TO_VALUE[mode]],
        )
        self.mark_ram_stale()
        await self.async_request_refresh()

    async def async_sync_time(self) -> None:
        """Manually synchronize GBO clock from Home Assistant."""
        if self.client.paused:
            raise GboError("GBO-Aku communication is disabled")

        if not self.data or "rtc_cfg" not in self.data:
            self.mark_ram_stale()
            await self.async_request_refresh()

        data = dict(self.data or {})
        rtc_cfg = int(
            data.get("rtc_cfg", 0x0E)
        ) & 0xFF

        written_at = await self._write_current_time(
            rtc_cfg,
        )

        self._apply_clock_to_data(
            data,
            written_at,
        )
        data["time_offset_seconds"] = 0
        data["last_time_sync"] = written_at.isoformat()

        self._last_time_check = time.monotonic()
        self.async_set_updated_data(data)

        self.mark_ram_stale()
        await self.async_request_refresh()

    async def async_refresh_eeprom(self) -> dict:
        """Read EEPROM immediately and update coordinator cached data."""
        if self.client.paused:
            raise GboError("GBO-Aku communication is disabled")

        registers = await self.client.read_holding_registers(
            EEPROM_START,
            EEPROM_COUNT,
        )
        data = dict(self.data or {})
        data.update(self._decode_eeprom(registers))
        self._last_eeprom = time.monotonic()
        self.async_set_updated_data(data)
        return data

    async def async_write_verified_eeprom(self, settings: dict) -> dict:
        """Apply only empirically verified EEPROM settings safely.

        Writes are intentionally never retried blindly. The entire read/modify/
        write/commit/readback sequence holds the transport lock so normal
        polling cannot be interleaved between EEPROM writes and the 0x55AA
        commit. The sequence mirrors the original HMI: changed words, current
        EEConfigWord, then checksum commit.
        """
        if self.client.paused:
            raise GboError("GBO-Aku communication is disabled")

        async with self.client.exclusive():
            registers = await self.client.read_holding_registers_unlocked(
                EEPROM_START,
                EEPROM_COUNT,
            )
            current_words = {
                address: _word_at(registers, EEPROM_START, address)
                for address in (20, 60, 64, 74, 86)
            }
            changed = build_verified_updates(current_words, settings)
            if not changed:
                data = dict(self.data or {})
                data.update(self._decode_eeprom(registers))
                self.async_set_updated_data(data)
                return data

            desired_config_word = changed.get(
                ADDR_CONFIG_WORD,
                current_words[ADDR_CONFIG_WORD],
            )
            expected_words = {**changed, ADDR_CONFIG_WORD: desired_config_word}
            commit_attempted = False
            try:
                # HMI writes every changed EEPROM word first. EEConfigWord is
                # always written immediately before the 0x55AA commit, so do
                # not write address 20 in this first pass.
                for address in sorted(a for a in changed if a != ADDR_CONFIG_WORD):
                    await self.client.write_multiple_registers_unlocked(
                        address,
                        [changed[address]],
                    )

                await self.client.write_multiple_registers_unlocked(
                    ADDR_CONFIG_WORD,
                    [desired_config_word],
                )
                commit_attempted = True
                await self.client.write_multiple_registers_unlocked(
                    ADDR_CHECKSUM,
                    [EEPROM_COMMIT_VALUE],
                )

                verify = await self.client.read_holding_registers_unlocked(
                    EEPROM_START,
                    EEPROM_COUNT,
                )

            except GboError as err:
                # Hold the lock over read-only recovery so polling or another
                # configuration transaction cannot interleave.
                await self.client.close()
                await asyncio.sleep(0.25)
                try:
                    recovery = await self.client.read_holding_registers_unlocked(
                        EEPROM_START,
                        EEPROM_COUNT,
                    )
                except GboError as readback_err:
                    self.mark_eeprom_stale()
                    raise GboError(
                        "EEPROM write status is uncertain; no automatic retry was "
                        f"performed and recovery readback failed: {readback_err}"
                    ) from err

                recovery_matches = all(
                    _word_at(recovery, EEPROM_START, address) == expected
                    for address, expected in expected_words.items()
                )
                recovery_checksum = _word_at(
                    recovery, EEPROM_START, ADDR_CHECKSUM
                )
                if (
                    commit_attempted
                    and recovery_matches
                    and recovery_checksum != EEPROM_COMMIT_VALUE
                ):
                    verify = recovery
                    _LOGGER.warning(
                        "GBO-Aku EEPROM commit was attempted and recovery "
                        "readback matches the requested words; no write retry "
                        "was performed"
                    )
                else:
                    data = dict(self.data or {})
                    data.update(self._decode_eeprom(recovery))
                    self.async_set_updated_data(data)
                    self.mark_eeprom_stale()
                    raise GboError(
                        "EEPROM write failed or remained uncertain; recovery "
                        "readback did not confirm a committed requested state. "
                        "No automatic write retry was performed."
                    ) from err

        for address, expected in expected_words.items():
            actual = _word_at(verify, EEPROM_START, address)
            if actual != expected:
                self.mark_eeprom_stale()
                raise GboError(
                    f"EEPROM verify failed at address {address}: "
                    f"read 0x{actual:04X}, expected 0x{expected:04X}"
                )

        self._last_eeprom_write = dt_util.now()
        self._eeprom_write_count += 1
        self._last_eeprom = time.monotonic()

        data = dict(self.data or {})
        data.update(self._decode_eeprom(verify))
        data["last_eeprom_write"] = self._last_eeprom_write
        data["eeprom_writes_by_ha"] = self._eeprom_write_count
        self.async_set_updated_data(data)

        _LOGGER.info(
            "GBO-Aku EEPROM configuration updated and verified: %s",
            ", ".join(
                f"{address}=0x{value:04X}"
                for address, value in sorted(changed.items())
            ),
        )
        return data

    async def async_backup_eeprom_to_flash(self) -> dict:
        """Back up the current EEPROM configuration to the MCU FLASH.

        This is an explicit maintenance action and is never called
        automatically after an EEPROM change. The wire sequence mirrors the
        original GreenBonO_HMI 3.0.3.6 capture:

        * read the complete 128-byte EEPROM configuration image (20..147),
        * write it to PageAVR at 0x0100 together with the captured FLASH
          control words,
        * poll until the controller changes the captured status byte P -> p,
        * issue the captured reset command,
        * reconnect and verify that EEPROM survived the restart unchanged.

        FLASH writes are never blindly retried. If the FC16 response is lost,
        only readback is used to decide whether the operation had started.
        """
        if self.client.paused:
            raise GboError("GBO-Aku communication is disabled")

        eeprom_image_start = 20
        eeprom_image_words = 64  # 128 bytes: EEPROM byte addresses 20..147
        flash_buffer_start = 0x0100
        flash_page_start = 0x3780
        flash_control_pending = 0x5042  # captured HMI value; P -> p when done
        flash_trailer = 0x3780
        flash_control_index = 65
        flash_status_pending = 0x50  # ASCII 'P'
        flash_status_done = 0x70     # ASCII 'p'
        flash_status_error = 0x65    # ASCII 'e'
        reset_address = 0x0182
        reset_value = 0x5200         # ASCII 'R' in byte 386

        snapshot: list[int] = []
        flash_started = False

        async with self.client.exclusive():
            snapshot = await self.client.read_holding_registers_unlocked(
                eeprom_image_start,
                eeprom_image_words,
            )
            if len(snapshot) != eeprom_image_words:
                raise GboError("Unexpected EEPROM image length before FLASH backup")

            flash_payload = snapshot + [
                flash_page_start,
                flash_control_pending,
                flash_trailer,
            ]

            try:
                await self.client.write_multiple_registers_unlocked(
                    flash_buffer_start,
                    flash_payload,
                )
                flash_started = True
            except GboError as err:
                # The write may have reached GBO even when its response was
                # lost. Never resend a FLASH write blindly. Reconnect and only
                # inspect PageAVR/control state.
                await self.client.close()
                await asyncio.sleep(0.25)
                try:
                    state = await self.client.read_holding_registers_unlocked(
                        flash_buffer_start,
                        len(flash_payload),
                    )
                except GboError as readback_err:
                    raise GboError(
                        "FLASH backup status is uncertain; no automatic write "
                        "retry was performed and PageAVR readback failed: "
                        f"{readback_err}"
                    ) from err

                status = (state[flash_control_index] >> 8) & 0xFF
                if (
                    state[:eeprom_image_words] == snapshot
                    and state[64] == flash_page_start
                    and state[66] == flash_trailer
                    and status in (flash_status_pending, flash_status_done)
                ):
                    flash_started = True
                    _LOGGER.warning(
                        "GBO-Aku FLASH write response was lost, but PageAVR "
                        "readback confirmed that the requested image/control "
                        "state reached the device; no write retry was performed"
                    )
                else:
                    raise GboError(
                        "FLASH backup write failed or remained uncertain; "
                        "PageAVR readback did not confirm the requested image. "
                        "No automatic write retry was performed."
                    ) from err

            if not flash_started:
                raise GboError("FLASH backup did not start")

            deadline = time.monotonic() + 8.0
            while True:
                if time.monotonic() >= deadline:
                    raise GboError(
                        "Timed out waiting for GBO FLASH status P -> p"
                    )
                try:
                    state = await self.client.read_holding_registers_unlocked(
                        flash_buffer_start,
                        len(flash_payload),
                    )
                except GboError:
                    # Reads are safe to retry. The original HMI also polls the
                    # buffer until the device reports completion.
                    await self.client.close()
                    await asyncio.sleep(0.25)
                    continue

                status = (state[flash_control_index] >> 8) & 0xFF
                if status == flash_status_done:
                    if state[:eeprom_image_words] != snapshot:
                        raise GboError(
                            "FLASH status reports success, but PageAVR image "
                            "does not match the EEPROM snapshot"
                        )
                    break
                if status == flash_status_error:
                    raise GboError("GBO reported FLASH programming error ('e')")
                if status != flash_status_pending:
                    raise GboError(
                        f"Unexpected GBO FLASH status 0x{status:02X}"
                    )
                await asyncio.sleep(0.25)

            # The original HMI resets GBO after successful programming. Do not
            # blindly retry this write either: a missing response can mean the
            # reset command was already accepted.
            try:
                await self.client.write_multiple_registers_unlocked(
                    reset_address,
                    [reset_value],
                )
            except GboError as err:
                _LOGGER.warning(
                    "GBO-Aku reset response after FLASH backup was lost; "
                    "the reset command will not be retried: %s",
                    err,
                )
            finally:
                await self.client.close()

            # Wait for the MCU/PE11 path to become available again. Only READs
            # are retried here.
            verify: list[int] | None = None
            last_err: GboError | None = None
            for _ in range(20):
                await asyncio.sleep(0.25)
                try:
                    verify = await self.client.read_holding_registers_unlocked(
                        eeprom_image_start,
                        eeprom_image_words,
                    )
                    break
                except GboError as err:
                    last_err = err
                    await self.client.close()

            if verify is None:
                raise GboError(
                    "FLASH was programmed, but GBO did not become readable "
                    f"after reset: {last_err}"
                )
            if verify != snapshot:
                raise GboError(
                    "EEPROM configuration changed across the FLASH backup/reset; "
                    "backup result cannot be accepted"
                )

        self._last_flash_backup = dt_util.now()
        self._flash_backup_count += 1
        self._last_eeprom = time.monotonic()

        data = dict(self.data or {})
        data.update(self._decode_eeprom(snapshot))
        data["last_flash_backup"] = self._last_flash_backup
        data["flash_backups_by_ha"] = self._flash_backup_count
        self.async_set_updated_data(data)

        _LOGGER.info(
            "GBO-Aku EEPROM configuration backed up to FLASH and verified "
            "after reset"
        )
        return data

    async def async_set_communication_enabled(self, enabled: bool) -> None:
        """Enable/disable HA communication and release PE11 when disabled."""
        await self.client.set_paused(not enabled)

        if not enabled:
            # Force ordinary entities unavailable immediately. Keep the
            # wall-clock diagnostic timestamp, but require a fresh live read
            # before becoming available again.
            self._last_live_success_mono = None
            data = dict(self.data or {})
            data["communication_status"] = "unavailable"
            self.async_set_updated_data(data)
            return

        self.mark_all_stale()
        await self.async_request_refresh()
