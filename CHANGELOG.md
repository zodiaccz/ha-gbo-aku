# Changelog

## v0.6.1

First public GitHub release for the GBO-Aku 3PI reference setup with firmware 3.021 and a Protoss PE11.

### Included

- Live monitoring, low-tariff status, RAM control, clock synchronization, and English and Czech UI translations.
- Verified EEPROM settings for surplus and NT/timer links and selected regulation parameters. Writes use read-modify-write, the HMI-style `EEConfigWord` write, `0x55AA` commit, and readback.
- Manual, confirmed backup of the current EEPROM settings to the FLASH recovery copy. The integration checks completion, resets the controller and verifies EEPROM again after reconnecting. The FLASH backup timestamp and counter are disabled by default.
- HACS and Hassfest validation workflows and the `gbo_aku.zip` install asset.

### Fixes during release preparation

- EEPROM configuration forms require a fresh read before showing values. An unavailable controller closes the EEPROM form with a connection error.
- EEPROM recovery reports failure when a write stops before the commit attempt, even if the changed words are already visible. Verification includes the `EEConfigWord`, and recovery reads stay under the exclusive transport lock.
- Turning communication off while TCP is still connecting discards the new connection before it sends a request.
- New setup entries require an explicit PE11 address. Existing config entries keep their settings and entity identities.

The EEPROM write allowlist, SSR bit mapping, RED auxiliary masks and explicit FLASH backup sequence are from the v0.6.1 baseline. EEPROM Save leaves the FLASH copy available for recovery.

### Installation

Install with Marketplace or HACS using the repository URL, or extract `gbo_aku.zip` directly into `/config/custom_components/gbo_aku/` and restart Home Assistant. See the README for connection and maintenance instructions.
