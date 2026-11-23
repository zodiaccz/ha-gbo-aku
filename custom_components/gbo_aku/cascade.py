"""SSR cascade helpers for the GBO-Aku 3PI firmware."""

from __future__ import annotations


def raw_to_percent(raw: int) -> float:
    """Convert an 8-bit PI output to percent."""
    raw = max(0, min(255, int(raw)))
    return round(raw * 100.0 / 255.0, 1)


def split_two_stage(
    raw: int,
    first_enabled: bool = True,
    second_enabled: bool = True,
) -> tuple[float, float]:
    """Split one 8-bit PI output over a two-stage SSR cascade.

    The GBO-Aku 3PI priority is:
      L1: SSR1 -> SSR4
      L2: SSR2 -> SSR5
      L3: SSR3 -> SSR6

    With both SSRs enabled, the 0..255 PI range represents the complete
    two-stage cascade: first SSR ramps 0..100 %, then stays at 100 %
    while the second SSR ramps 0..100 %.

    If only one member of the pair is enabled, the full 0..255 range is
    mapped to that remaining SSR.
    """
    raw = max(0, min(255, int(raw)))
    first_enabled = bool(first_enabled)
    second_enabled = bool(second_enabled)

    if not first_enabled and not second_enabled:
        return 0.0, 0.0

    if first_enabled and second_enabled:
        total = raw * 200.0 / 255.0
        first = min(total, 100.0)
        second = max(total - 100.0, 0.0)
        return round(first, 1), round(second, 1)

    pct = raw_to_percent(raw)
    if first_enabled:
        return pct, 0.0
    return 0.0, pct


def cascade_total_percent(
    raw: int,
    first_enabled: bool = True,
    second_enabled: bool = True,
) -> float:
    """Return total cascade position in percent of one nominal SSR load."""
    a, b = split_two_stage(raw, first_enabled, second_enabled)
    return round(a + b, 1)
