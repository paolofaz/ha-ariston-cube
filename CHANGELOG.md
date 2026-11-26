# Changelog

## 1.4.1 — 2026-11-26

- Add plant-scoped reauthentication and distinguish HTTP 403/405 from authentication failures.
- Support explicit `entry_id` selection for services when multiple boilers are configured.
- Retry AUTO restoration only if the zone-mode command was proven not to have been transmitted, with at most three retries and cooldown-aware scheduling.
- Notify the user if AUTO restoration remains unconfirmed.
