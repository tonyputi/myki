# MyKi for Home Assistant

<img src="docs/assets/myki-icon.png" width="96" align="right" alt="MyKi">

[![CI](https://github.com/tonyputi/myki/actions/workflows/ci.yml/badge.svg)](https://github.com/tonyputi/myki/actions/workflows/ci.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Unofficial Home Assistant integration for **Allterco MyKi GPS trackers** (first supported device: **MyKi Spot**). It uses the same cloud API as the MyKi Spot app — no vendor app needed on any phone you don't want it on.

> ⚠️ Unofficial, not affiliated with Allterco. Your credentials are stored in Home Assistant (Settings → Device & Services) exactly like any other cloud integration.

## What you get

Per tracker (each kid gets a **device** named after the tracker nickname):

| Entity | Description |
|---|---|
| `device_tracker.<kid>` | Last reported location and accuracy (GPS, WiFi or cellular) |
| `sensor.<kid>_zone` | The tracker's own safe zones: **"Home" / "School" / … / "Away"** |
| `sensor.<kid>_battery` | Battery % |
| `binary_sensor.<kid>_online` | Tracker online/offline |
| `sensor.<kid>_steps_today` | Today's step count |
| `event.<kid>_events` | SOS alarm / low battery / safe zone events (automation-ready) |
| `button.<kid>_live_tracking` | Start live tracking using the app's default duration parameter |
| `sensor.<kid>_live_tracking_seconds_left` | Live tracking countdown |
| `binary_sensor.<kid>_fresh_data` | Device has reported within 30 min |
| `sensor.<kid>_gsm_signal` | GSM signal % (diagnostic) |
| `button.<kid>_find` | Ring the tracker |
| `switch.<kid>_flashlight` | App flashlight / temporary LED command |
| `sensor.<kid>_safe_zone_1` / `_safe_zone_2` | Shared zone name; coordinates, radius in meters, enabled state and ring mode as attributes |
| `sensor.<kid>_do_not_disturb` | First DND period; all four cloud periods as attributes |
| `sensor.<kid>_alarm_1` … `_alarm_3` | Shared alarm time; enabled state and selected weekdays as attributes |

The zone sensor is calculated from the reported position and active MyKi safe zones. Invalid coordinates or malformed zone configuration produce `unknown`, not `away`; disabled zones are ignored. Automations should ignore `unknown`/`unavailable` transitions and allow for tracker reporting and cloud polling delays.

**Services** (Developer Tools → Actions):

```yaml
# Make the tracker ring
action: myki.find
target:
  entity_id: device_tracker.child
```

```yaml
# Make the tracker call its current shared SOS 1 contact
action: myki.make_call
target:
  entity_id: device_tracker.child
data:
  contact: sos_1
```

## Configure a tracker

Use **Settings → Devices & services → MyKi → Configure → Tracker settings**. Choose the tracker once, then a section:

- **Contacts:** three SOS and seven app-visible whitelist slots; choose one slot to edit or clear.
- **Audio and status light:** ring mode, ringtone, ring/call volume and default/disabled status LED.
- **Device and battery:** operating mode, battery saving, tracker nickname and SIM number.
- **Safe zones:** choose zone 1 or 2; the native HA map shows its current center and radius in meters. Edit name, center, circle radius, activation and audio/vibration profile.
- **Alarms and Do not disturb:** choose one of three alarms (enabled, minute-precision time, weekdays), or DND (enabled, start/end).

These are native menu sections, not tabs or a custom frontend. Values are freshly read when opening an editor; nothing is sent until **Submit**. Each editor identifies the selected tracker and setting. A successful save verifies the cloud value and closes the form. Reopen Configure to edit another setting. An uncertain save also closes the draft with a warning: inspect current values before retrying. Missing/malformed data is not replaced with invented defaults. Tracker preferences, contact numbers, locations and schedules are never saved in the entry's HA options; only integration preferences such as polling are stored there.

The device page is for state, diagnostic information and quick commands (Find, live tracking, flashlight), not a second default settings editor. Zone/DND/alarm sensors remain read-only summaries. Existing structured actions remain available to automations and Developer Tools; no separate frontend is required.

### Upgrade: settings controls moved

The old `number` volume sliders, `select` ring/ringtone/mode controls, status-LED/battery switches and `text` contacts/nickname/SIM entities are **removed**, not hidden or disabled compatibility controls. Their obsolete platform implementations and translations are deleted. Setup removes their registry entries even when renamed, disabled or associated with a tracker no longer on the account, without writing cloud settings. They cannot be re-enabled. Dashboard cards and automations referencing these removed entities must be updated; interactive edits use Configure. Existing Find/live-tracking/flashlight controls, location, diagnostics, events and structured zone/schedule/call actions are unchanged.

## Shared contacts

Edit contacts through **Configure → Tracker settings → Contacts**; they read and write the same MyKi cloud slots as the app, not a separate HA address book. App changes appear on the next successful refresh. Enter digits, optionally prefixed with `+`; new international numbers use the app's `00` format. An empty value clears a slot. Equivalent `+`/`00` values do not cause unnecessary rewrites.

The app exposes three SOS and seven whitelist numbers. Whitelist writes require a complete group of five: the integration reads fresh cloud data and preserves the other entries, including the three cloud slots the app does not show. Missing/malformed groups and offline trackers are not overwritten. Edits to a slot changed since the last HA refresh are rejected. Only cloud readback is displayed; rejection, timeout or different readback raises an error rather than showing optimistic success. After an uncertain result, refresh and inspect the app before retrying; there is no automatic retry or rollback.

**Avoid editing the same whitelist group simultaneously in HA and the app.** HA serializes its own edits and checks readback, but the vendor API offers no conditional-write/version token: an app edit between HA's read and write cannot be prevented atomically. Cloud confirmation is not proof that hardware has applied the setting. Physical-device/app write verification remains tracked in #27.

MyKi cloud is the source of truth for tracker settings and contacts; HA does not keep a separate calling destination. To initiate a call from HA, use `myki.make_call` with the contact specified for that execution, as above. Its current number is resolved from the cloud. The deprecated `phone` action argument is removed; automations must specify `contact` (for example, `sos_1`). There is one calling destination format, resolved from the current shared cloud slot on every execution.

**Upgrade:** the HA-only **Call contact** selector and **Call me** button are removed, together with their saved `call_contacts` and legacy `call_me_number` options. Their entity-registry entries are cleaned up automatically on setup. Automations or dashboards referencing these removed entities must be updated; use the existing `myki.make_call` action for explicit calls. No SOS/whitelist cloud contacts are inserted, changed or deleted by this cleanup, and the physical SOS button is unaffected.

**Privacy:** settings forms contain personal data; restrict HA access, debug logging and backups. Removing contact text entities does not erase any previously recorded values from Recorder or backups. MyKi diagnostics do not include the contacts; MyKi-generated errors do not include numbers.

### Device-page ordering

Home Assistant sorts the standard device panels by display name. Read-only configuration summaries use Schedules/Zone group prefixes; diagnostics use Cloud, Reception and Tracking, and the flashlight uses Lights. Cell towers, GPS satellites, GSM signal and WiFi networks share the Reception prefix. These are name groups, not custom subpanels. Remaining state/diagnostic entity IDs and user-customized names are preserved, including on reload; custom names may sort outside the default groups. Example IDs below retain their original bases.

Zone, DND and alarm sensors show configuration; edit them through Configure as described above, not by clicking the read-only sensor state. Structured `myki.set_safe_zone`, `myki.set_dnd` and `myki.set_alarm` actions remain available for automation.

## Shared personalization

Ring mode, ringtone and status LED read the same global command-state fields as the MyKi app. Ring mode offers sound and vibration, sound only, vibration only and mute; ringtone offers Classic, Playtime and Twinkle. When the cloud omits the ringtone field, HA displays Classic, matching the app's initial value; a present but invalid value remains unknown. This fallback does not write a setting to the tracker. No selection is saved in HA options. Reopening an editor reads current app/cloud values. Polling also updates the read-only state summaries.

Each change reads the current cloud state, rejects a stale edit or offline tracker, writes only the selected setting and requires matching cloud readback. Except for the app's absent-ringtone Classic default described above, missing/unsupported values display `unknown` and are not silently replaced. No optimistic state, automatic retry or rollback is used; after an uncertain result, refresh and inspect the app before retrying. Local commands and polling are serialized, but the vendor API has no conditional writes to prevent simultaneous app edits atomically.

The status LED editor offers **1** for default status indication or **0** for disabled, never the temporary LED-party value **2**. During temporary mode no default choice is preselected because the stored default preference cannot be inferred; explicitly saving a choice replaces that mode. Default indication does not promise a continuously lit LED.

These are global settings, not per-zone melodies. Safe-zone profiles are left untouched; hardware precedence with zones/DND and app/cloud/tracker round-trip behavior remain unverified under #41. Cloud readback is not proof that the physical tracker has applied a change. No automatic sound preview is played.

## Remaining shared Spot settings

The app's quick settings are shortcuts, not duplicate settings. Battery save and operating mode use cloud `settings.battery_save_mode` (0/1) and `settings.mode` (`sos`/`pet`/`asset`). Selecting a mode changes device behavior, not its hardware model. The app describes Asset mode as WiFi/LBS positioning with on-demand GPS and optional disabled calls; do not assume identical reporting, call availability or battery life between modes. After a mode change, the integration checks known contacts, zones and other configuration for unexpected changes and reports them without attempting rollback. Cloud readback cannot prevent device-side side effects.

The separate flashlight switch follows the app's temporary LED command: on sends **2**, off restores default **1** only when the flashlight was active. It does not remember a previous LED preference; switching an already-off flashlight off leaves a disabled status LED alone. Temporary-mode expiry and hardware effects need final verification.

Use **Configure → Tracker settings** for interactive zone/map and schedule editors. For automation, use the structured actions in **Developer Tools → Actions**. Each action targets a MyKi `device_tracker`, reads fresh state, rejects stale/offline edits, preserves unedited siblings and unknown zone fields, and verifies cloud readback. Omit fields to keep their current cloud values. No local schedule, cached enable-time preference, automatic retry or rollback is created. Empty/malformed schedules are not replaced with invented defaults.

```yaml
# Change only the first official zone radius and ring mode.
action: myki.set_safe_zone
target:
  entity_id: device_tracker.child
data:
  zone: safe_zone_1
  radius: 70  # meters; cloud kilometers are converted internally
  ring_mode: "4"  # 1 sound+vibration, 2 sound, 3 vibration, 4 mute
```

`myki.set_safe_zone` also accepts `name`, `latitude`, `longitude` and `enabled`. Only official slots `safe_zone_1` and `safe_zone_2` are writable. Creating an empty slot requires all fields explicitly. Zone color is stored on the Android phone, not in the examined zone cloud write; it is not exposed as a fake shared setting.

```yaml
action: myki.set_dnd
target:
  entity_id: device_tracker.child
data:
  enabled: true
  start: "08:00"
  end: "13:00"
```

DND edits **period 1 only**, preserving periods 2–4. Disabling writes the app sentinel `00:00-00:00`; other periods can still restrict calls. Both times are needed to re-enable a disabled period, because HA does not store a separate remembered interval. Equal start/end times are rejected when enabling. Overnight ranges are serialized without timezone conversion; physical overnight, DST and timezone behavior remain unverified. The app says DND restricts incoming calls while alarms remain active; this is app guidance, not a hardware-tested guarantee.

```yaml
action: myki.set_alarm
target:
  entity_id: device_tracker.child
data:
  alarm: alarm_1
  enabled: true
  time: "07:00"
  weekdays: [mon, tue, wed, thu, fri]
```

Alarms accept `alarm_1`–`alarm_3`. Weekdays use `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat`; enabling requires at least one selected day. The app's opaque alarm field and freshly read sibling slots are preserved. All times are minute-precision tracker wall-clock times (`HH:MM`), not HA-local or UTC timestamps. These configure tracker alarms, not HA alarm automations.

The tracker nickname and SIM-number settings edit the vendor account's device metadata through the app's paired write, preserving the freshly read other field. This does not reprogram a SIM, change an SOS contact or dial a call. Phone numbers require digits with an optional leading `+`; missing/invalid paired data is not silently replaced. Existing HA device/entity names and user customizations are not forcibly renamed; HA's default device name is refreshed on integration reload. Editing an HA display name alone still does not change the cloud nickname.

### Explicit power actions

`myki.power_off` and `myki.restart` require `confirm: true` on every execution. They are actions, not ordinary dashboard buttons or custom confirmation dialogs. **Power off stops tracking/calls and requires physical access to turn the tracker on; no remote power-on is known.** Restart temporarily interrupts service and could require physical recovery. Request success means cloud acceptance, not verified shutdown, reboot or configuration retention; HA does not optimistically mark the tracker offline or retry an uncertain command. Never schedule these as an unattended safety mechanism.

Factory reset and account-device deletion remain app-only: potential configuration loss, re-pairing/unlinking and recovery are not sufficiently established for safe HA exposure. They have no HA action or button. Account administration, provisioning and full vendor historical browsing remain app-managed; HA entity rename does not change the vendor nickname, and Recorder is not vendor history backfill.

### Phone notifications are separate

The app's Zone in, Zone out, Low battery and SOS pressed switches control the Android phone's notification registration. They are not shared tracker switches: HA does not read/change that phone registration, extract FCM tokens or impersonate the phone. HA can independently automate from computed zone changes, battery/online sensors and polled vendor events; this is not equivalent to real-time vendor push. No vendor event-name strings are assumed from translated on-screen messages.

### One final acceptance check

After human merge, normal release/HACS installation and an approved HA Core restart, perform one controlled validation session instead of testing between feature PRs:

1. Read-only app/HA comparison on both trackers: contacts, both zones, modes, battery saving, audio/LED and schedules.
2. Separately authorize each reversible write on one tracker, record the original value, confirm HA→app and app→HA behavior, verify unrelated settings and restore it. Avoid simultaneous edits from HA/app.
3. Check zone/ring-mode precedence and restoration, tracker timezone/DST/overnight schedules, weekday ordering and actual alarm/LED behavior. Cloud storage alone is not hardware proof.
4. Contact writes, calls/SOS, sounds, flashlight, mode changes and power actions need explicit scope before execution. Power-off/restart recovery must be arranged first. Factory reset and deletion are excluded.
5. Record results against the existing work items, and close only the acceptance criteria actually verified. Other backends, extra zones, Core submission, publication and sponsorship are separate future work, not blockers for this Spot batch.

Private screenshots, account details, phone numbers and real locations must not be published in issues, tests or documentation. The new zone/schedule state attributes are visible to HA users and may be stored by Recorder; apply the same privacy/access controls as tracker locations and contacts.

## Attach a tracker to a person

The trackers work with HA people: **Settings → People → *your kid* → add the MyKi tracker**, next to the tablet's tracker. Home Assistant combines the sources using its [Person presence rules](https://www.home-assistant.io/integrations/person/); it does not always select the most recent report.

## Automation ideas

Event entities poll the vendor history and do not replay existing alarms when the integration loads. After history rotation, only events with numeric timestamps strictly newer than the last seen event are emitted; tied or unrecognized timestamps may be skipped. This is not a guaranteed or real-time safety notification system.

```yaml
# Replace the entity, zone name and notification action with your own.
alias: School presence reminder
triggers:
  - trigger: time
    at: "08:45:00"
conditions:
  - condition: time
    weekday: [mon, tue, wed, thu, fri]
  - condition: template
    value_template: "{{ states('sensor.child_zone') not in ['School', 'unknown', 'unavailable'] }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: "The tracker is not reporting School."
```

- Kid left `Home` on a school morning → "on the bus" notification
- Battery < 20% → evening charge reminder
- Tracker offline on a school day → forgot/flat battery alert

More in [docs/CAPABILITIES.md](docs/CAPABILITIES.md).

## Installation

Requires **Home Assistant 2026.11.0 or newer**. Earlier releases are not supported.

**HACS:** HACS → ⋮ Custom repositories → `https://github.com/tonyputi/myki` (category *Integration*), install **MyKi**, restart.

**Manual:** copy `custom_components/myki/` into your Home Assistant `config/custom_components/myki/`, restart.

Then enter the email and password of your MyKi Spot account.

Configure on the integration card opens **Tracker settings** (the shared cloud editors described above) or **Integration polling** (seconds between updates, default 60, minimum 10; the vendor app polls every 10 s).

## How it works

Reverse-engineered REST API of the MyKi Spot cloud (`spot.myki.pet`, HTTP Basic auth). The integration polls `GET /api/watch/app-data` per tracker: position, battery, steps, online state and the safe zones configured in the app. Full capability map: [docs/CAPABILITIES.md](docs/CAPABILITIES.md).

## Development

Tests target Home Assistant 2026.11.0 on Python 3.14.2 or newer in the 3.14 series. Use [uv](https://docs.astral.sh/uv/) and an environment outside the checkout:

```bash
uv venv --python 3.14 /tmp/myki-tests
source /tmp/myki-tests/bin/activate
uv pip install -r requirements_test.txt
pytest && ruff check .
```

The official `pytest-homeassistant==2026.11.0` package pins the tested HA version. CI uses the same requirements; no compatibility code for older HA versions is maintained. CI also runs the official hassfest validator. These checks validate this custom integration, not acceptance into Home Assistant Core. Vendor event timestamp semantics, exact live-tracking duration and full hardware behavior still require live verification; no tracker commands are sent by the tests.

## Supported devices

| Product | Type | Link | Status |
|---|---|---|---|
| **MyKi Spot** | GPS tracker | [mykifamily.com/myki-spot](https://mykifamily.com/myki-spot) | ✅ supported |

Other MyKi products and backends have not been verified and are not supported.

The integration identifies known models from the device firmware. Diagnostics contain only anonymous model, battery, signal, step and online status, plus account polling status; raw vendor payloads, identifiers, contacts and locations are not exported. For model-identification issues, report the model and firmware version shown on the device page, without sharing personal data.

## Trademark

MyKi and the MyKi logo are trademarks of Allterco Consulting Ltd.
The icon used in this README is the official MyKi asset from mykifamily.com.

## License

[MIT](LICENSE)
