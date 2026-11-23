from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Vendor byte addresses of EEPROM words used by the verified configuration UI.
ADDR_CONFIG_WORD = 20
ADDR_RELAYS_ENABLE = 60
ADDR_SSR_ENABLE = 64
ADDR_FLAGS = 74
ADDR_CHECKSUM = 76
ADDR_WEEKLY_SCHEDULE = 86

EEPROM_COMMIT_VALUE = 0x55AA

# Physical SSR numbering does not follow the bit order. The GBO/HMI bit order
# follows the regulator topology: L1 (SSR1,SSR4), L2 (SSR2,SSR5), L3 (SSR3,SSR6).
SSR_BIT_BY_NUMBER: dict[int, int] = {
    1: 0,
    4: 1,
    2: 2,
    5: 3,
    3: 4,
    6: 5,
}
SSR_MASK_BY_NUMBER = {number: 1 << bit for number, bit in SSR_BIT_BY_NUMBER.items()}

RELAY_MASK_BY_NUMBER = {number: 1 << (number - 1) for number in range(1, 6)}

# HMI/FW 3.021 empirically writes these auxiliary RelaysEnable high-byte bits
# together with the corresponding red SSR links. They are not user-facing.
RED_SSR_AUX_MASK_BY_NUMBER: dict[int, int] = {
    1: 0x2000,
    4: 0x4000,
    2: 0x8000,
}
RED_SSR_AUX_ALL = 0xE000

# RelaysEnable low-byte verified flags.
RELAY_NT_BYPASS = 0x0040
RELAY_SSR_SLOW = 0x0080

# SSREnable low-byte verified non-SSR flags.
SSR_UDC_CONTROL = 0x0040
SSR_UDC_INVERT = 0x0080

# EEnewFlags in high byte of address 74. These three were verified against HMI.
# They are active-low in FW 3.021/HMI 3.0.3.
FLAG_HALF_PERIOD = 0x02
FLAG_AUTO_DST = 0x04
FLAG_STOP_AFTER_DARK = 0x80

# K5 mode is stored in bits b3:b2 of EEConfigWord low byte. The high byte is
# the bitwise complement of the low byte.
K5_MODE_BITS = {
    "surplus_pump": 0x08,   # b3:b2 = 10
    "timer_only": 0x0C,     # b3:b2 = 11, SH1 + NT only
    "cascade": 0x04,        # b3:b2 = 01, fifth cascade relay
}
K5_BITS_TO_MODE = {value: key for key, value in K5_MODE_BITS.items()}

WEEKDAY_MASKS = {
    "sunday": 0x01,
    "monday": 0x02,
    "tuesday": 0x04,
    "wednesday": 0x08,
    "thursday": 0x10,
    "friday": 0x20,
    "saturday": 0x40,
}


def ssr_mask(number: int) -> int:
    return SSR_MASK_BY_NUMBER[number]


def relay_mask(number: int) -> int:
    return RELAY_MASK_BY_NUMBER[number]


def decode_verified_config(
    config_word: int,
    relays_enable: int,
    ssr_enable: int,
    flags_word: int,
    weekly_schedule: int,
) -> dict[str, Any]:
    """Decode only configuration fields verified on FW 3.021/HMI 3.0.3."""
    relay_low = relays_enable & 0xFF
    relay_high = (relays_enable >> 8) & 0xFF
    ssr_low = ssr_enable & 0xFF
    ssr_high = (ssr_enable >> 8) & 0xFF
    flags = (flags_word >> 8) & 0xFF
    days = weekly_schedule & 0x7F

    data: dict[str, Any] = {
        "relay_surplus_mask": relay_low & 0x1F,
        "relay_nt_timer_mask": relay_high & 0x1F,
        "relay_red_aux_mask": relay_high & 0xE0,
        "ssr_surplus_mask": ssr_low & 0x3F,
        "ssr_nt_timer_mask": ssr_high & 0x3F,
        "nt_bypass_enabled": bool(relays_enable & RELAY_NT_BYPASS),
        "ssr_slow_modulation_enabled": bool(relays_enable & RELAY_SSR_SLOW),
        "udc_control_enabled": bool(ssr_enable & SSR_UDC_CONTROL),
        "udc_control_inverted": bool(ssr_enable & SSR_UDC_INVERT),
        "half_period_modulation_enabled": not bool(flags & FLAG_HALF_PERIOD),
        "automatic_dst_enabled": not bool(flags & FLAG_AUTO_DST),
        "stop_after_dark_enabled": not bool(flags & FLAG_STOP_AFTER_DARK),
        "regulation_start_delay": (weekly_schedule >> 8) & 0xFF,
        "night_days_mask": days,
        "k5_mode": K5_BITS_TO_MODE.get((config_word & 0xFF) & 0x0C, "unknown"),
    }

    for number in range(1, 6):
        data[f"relay_k{number}_surplus_enabled"] = bool(
            relay_low & relay_mask(number)
        )
        data[f"relay_k{number}_nt_timer_enabled"] = bool(
            relay_high & relay_mask(number)
        )

    for number in range(1, 7):
        bit = ssr_mask(number)
        data[f"ssr{number}_surplus_enabled"] = bool(ssr_low & bit)
        data[f"ssr{number}_nt_timer_enabled"] = bool(ssr_high & bit)

    for day, bit in WEEKDAY_MASKS.items():
        data[f"night_{day}_enabled"] = bool(days & bit)

    return data


def _set_bool_bit(value: int, mask: int, enabled: bool) -> int:
    if enabled:
        return value | mask
    return value & ~mask


def build_verified_updates(
    current_words: Mapping[int, int],
    settings: Mapping[str, Any],
) -> dict[int, int]:
    """Build EEPROM word updates from verified logical settings.

    Only keys present in ``settings`` are changed. Unrelated/reserved bits are
    preserved with read-modify-write semantics.
    """
    config_word = int(current_words[ADDR_CONFIG_WORD]) & 0xFFFF
    relays = int(current_words[ADDR_RELAYS_ENABLE]) & 0xFFFF
    ssr = int(current_words[ADDR_SSR_ENABLE]) & 0xFFFF
    flags_word = int(current_words[ADDR_FLAGS]) & 0xFFFF
    weekly = int(current_words[ADDR_WEEKLY_SCHEDULE]) & 0xFFFF

    # Black/surplus K1..K5, preserving b5..b7 and the entire high byte.
    relay_low = relays & 0xFF
    for number in range(1, 6):
        key = f"relay_k{number}_surplus_enabled"
        if key in settings:
            relay_low = _set_bool_bit(
                relay_low,
                relay_mask(number),
                bool(settings[key]),
            )
    relays = (relays & 0xFF00) | relay_low

    # Red/NT+timer K1..K5, preserving auxiliary red-SSR bits b5..b7.
    relay_high = (relays >> 8) & 0xFF
    for number in range(1, 6):
        key = f"relay_k{number}_nt_timer_enabled"
        if key in settings:
            relay_high = _set_bool_bit(
                relay_high,
                relay_mask(number),
                bool(settings[key]),
            )
    relays = (relay_high << 8) | (relays & 0xFF)

    # Black/surplus SSR1..SSR6 using topology bit order, preserving Udc b6/b7.
    ssr_low = ssr & 0xFF
    for number in range(1, 7):
        key = f"ssr{number}_surplus_enabled"
        if key in settings:
            ssr_low = _set_bool_bit(ssr_low, ssr_mask(number), bool(settings[key]))
    ssr = (ssr & 0xFF00) | ssr_low

    # Red/NT+timer SSR1..SSR6. If any red SSR key is present, recompute the
    # HMI's auxiliary RelaysEnable high b5..b7 from the final red SSR state.
    red_ssr_touched = any(
        f"ssr{number}_nt_timer_enabled" in settings
        for number in range(1, 7)
    )
    ssr_high = (ssr >> 8) & 0xFF
    for number in range(1, 7):
        key = f"ssr{number}_nt_timer_enabled"
        if key in settings:
            ssr_high = _set_bool_bit(ssr_high, ssr_mask(number), bool(settings[key]))
    ssr = (ssr_high << 8) | (ssr & 0xFF)

    if red_ssr_touched:
        aux = 0
        for number, aux_mask in RED_SSR_AUX_MASK_BY_NUMBER.items():
            if ssr_high & ssr_mask(number):
                aux |= aux_mask
        relays = (relays & ~RED_SSR_AUX_ALL) | aux

    # Verified global flags in addr60/64 low byte.
    if "nt_bypass_enabled" in settings:
        relays = _set_bool_bit(relays, RELAY_NT_BYPASS, bool(settings["nt_bypass_enabled"]))
    if "ssr_slow_modulation_enabled" in settings:
        relays = _set_bool_bit(relays, RELAY_SSR_SLOW, bool(settings["ssr_slow_modulation_enabled"]))
    if "udc_control_enabled" in settings:
        ssr = _set_bool_bit(ssr, SSR_UDC_CONTROL, bool(settings["udc_control_enabled"]))
    if "udc_control_inverted" in settings:
        ssr = _set_bool_bit(ssr, SSR_UDC_INVERT, bool(settings["udc_control_inverted"]))

    # Active-low verified EEnewFlags in addr74 high byte.
    flags = (flags_word >> 8) & 0xFF
    active_low_settings = (
        ("half_period_modulation_enabled", FLAG_HALF_PERIOD),
        ("automatic_dst_enabled", FLAG_AUTO_DST),
        ("stop_after_dark_enabled", FLAG_STOP_AFTER_DARK),
    )
    for key, bit in active_low_settings:
        if key in settings:
            flags = _set_bool_bit(flags, bit, not bool(settings[key]))
    flags_word = (flags << 8) | (flags_word & 0xFF)

    # Weekly NT schedule mask + empirically verified regulation-start delay.
    days = weekly & 0xFF
    for day, bit in WEEKDAY_MASKS.items():
        key = f"night_{day}_enabled"
        if key in settings:
            days = _set_bool_bit(days, bit, bool(settings[key]))
    if "regulation_start_delay" in settings:
        delay = int(settings["regulation_start_delay"])
        if delay < 0 or delay > 0xFF:
            raise ValueError("regulation_start_delay must be 0..255")
        weekly = (delay << 8) | days
    else:
        weekly = (weekly & 0xFF00) | days

    # Verified K5 mode. Preserve all other low-byte bits and regenerate the
    # documented complement in the high byte.
    if "k5_mode" in settings:
        mode = str(settings["k5_mode"])
        if mode == "unknown":
            pass
        elif mode in K5_MODE_BITS:
            low = config_word & 0xFF
            low = (low & ~0x0C) | K5_MODE_BITS[mode]
            config_word = (((~low) & 0xFF) << 8) | low
        else:
            raise ValueError(f"Unsupported K5 mode: {mode}")

    desired = {
        ADDR_CONFIG_WORD: config_word,
        ADDR_RELAYS_ENABLE: relays,
        ADDR_SSR_ENABLE: ssr,
        ADDR_FLAGS: flags_word,
        ADDR_WEEKLY_SCHEDULE: weekly,
    }

    return {
        address: value
        for address, value in desired.items()
        if value != (int(current_words[address]) & 0xFFFF)
    }
