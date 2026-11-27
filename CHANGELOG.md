# Changelog

## 1.4.2 — 2026-11-27

- Bind weekly-card preview and confirmed write actions to the selected weekly sensor's config entry, preventing cross-plant edits.
- Recover authentication during read-only zone-mode preflight; classify a failed preflight as not sent without retrying an ambiguous write.
- Restore unresolved AUTO notifications on startup and dismiss them after resolution or an explicit successful replacement command.
- Supply English runtime translations and refresh the weekly card resource version.

## 1.4.1 — 2026-11-26

- Add plant-scoped reauthentication and distinguish HTTP 403/405 from authentication failures.
- Support explicit `entry_id` selection for services when multiple boilers are configured.
- Retry AUTO restoration only if the zone-mode command was proven not to have been transmitted, with at most three retries and cooldown-aware scheduling.
- Notify the user if AUTO restoration remains unconfirmed.
