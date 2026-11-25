# MyKi Spot hardware acceptance

This maintainer checklist is not part of installation. It describes checks to perform, not checks already completed.

After human merge, normal release/HACS installation and an approved HA Core restart, perform one controlled validation session instead of testing between feature PRs:

1. Read-only app/HA comparison on both trackers: contacts, both zones, modes, battery saving, audio/LED and schedules.
2. Separately authorize each reversible write on one tracker, record the original value, confirm HA→app and app→HA behavior, verify unrelated settings and restore it. Avoid simultaneous edits from HA/app.
3. Check zone/ring-mode precedence and restoration, tracker timezone/DST/overnight schedules, weekday ordering and actual alarm/LED behavior. Cloud storage alone is not hardware proof.
4. Contact writes, calls/SOS, sounds, flashlight, mode changes and power actions need explicit scope before execution. Power-off/restart recovery must be arranged first. Factory reset and deletion are excluded.
5. Record results against the existing work items, and close only the acceptance criteria actually verified. Other backends, extra zones, Core submission, publication and sponsorship are separate future work, not blockers for this Spot batch.

Private screenshots, account details, phone numbers and real locations must not be published in issues, tests or documentation. The new zone/schedule state attributes are visible to HA users and may be stored by Recorder; apply the same privacy/access controls as tracker locations and contacts.
