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
| `number.<kid>_ring_volume` / `number.<kid>_call_volume` | Volume sliders (config) |
| `select.<kid>_ring_mode` | Shared sound/vibration mode (config) |
| `select.<kid>_ringtone` | Shared Classic / Playtime / Twinkle ringtone (config) |
| `switch.<kid>_status_led` | Shared default status LED indication (config) |
| `text.<kid>_sos_1` … `sos_3` | Shared MyKi SOS numbers (config) |
| `text.<kid>_whitelist_1` … `whitelist_7` | Shared app-visible whitelist numbers (config) |

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

## Shared contacts

Edit the SOS/whitelist text entities on each device; they read and write the same MyKi cloud slots as the app, not a separate HA address book. App changes appear on the next successful refresh. Enter digits, optionally prefixed with `+`; new international numbers use the app's `00` format. An empty value clears a slot. Equivalent `+`/`00` values do not cause unnecessary rewrites.

The app exposes three SOS and seven whitelist numbers. Whitelist writes require a complete group of five: the integration reads fresh cloud data and preserves the other entries, including the three cloud slots the app does not show. Missing/malformed groups and offline trackers are not overwritten. Edits to a slot changed since the last HA refresh are rejected. Only cloud readback is displayed; rejection, timeout or different readback raises an error rather than showing optimistic success. After an uncertain result, refresh and inspect the app before retrying; there is no automatic retry or rollback.

**Avoid editing the same whitelist group simultaneously in HA and the app.** HA serializes its own edits and checks readback, but the vendor API offers no conditional-write/version token: an app edit between HA's read and write cannot be prevented atomically. Cloud confirmation is not proof that hardware has applied the setting. Physical-device/app write verification remains tracked in #27.

MyKi cloud is the source of truth for tracker settings and contacts; HA does not keep a separate calling destination. To initiate a call from HA, use `myki.make_call` with the contact specified for that execution, as above. Its current number is resolved from the cloud. Existing automations using `phone` still work only if that number matches an app-visible shared contact (`+`/`00` compare equivalently).

**Upgrade:** the HA-only **Call contact** selector and **Call me** button are removed, together with their saved `call_contacts` and legacy `call_me_number` options. Their entity-registry entries are cleaned up automatically on setup. Automations or dashboards referencing these removed entities must be updated; use the existing `myki.make_call` action for explicit calls. No SOS/whitelist cloud contacts are inserted, changed or deleted by this cleanup, and the physical SOS button is unaffected.

**Privacy:** contact text values are personal data in HA states and may be recorded in history or included in HA debug logs/backups. Restrict HA access and exclude these entities from Recorder if needed. MyKi diagnostics do not include the contacts; MyKi-generated errors do not include numbers.

## Shared personalization

Ring mode, ringtone and status LED read the same global command-state fields as the MyKi app. Ring mode offers sound and vibration, sound only, vibration only and mute; ringtone offers Classic, Playtime and Twinkle. No selection is saved in HA options. App changes appear on the next successful refresh, and existing volume entities are unchanged.

Each change reads the current cloud state, rejects a stale edit or offline tracker, writes only the selected setting and requires matching cloud readback. Missing/unsupported values display `unknown` and are not silently replaced. No optimistic state, automatic retry or rollback is used; after an uncertain result, refresh and inspect the app before retrying. Local commands and polling are serialized, but the vendor API has no conditional writes to prevent simultaneous app edits atomically.

The LED switch sends **1** for default status indication or **0** for disabled, never the temporary LED-party value **2**. During temporary mode, the switch displays `unknown` because the stored default preference cannot be inferred; an explicit on/off action replaces that mode. The switch does not promise a continuously lit LED.

These are global settings, not per-zone melodies. Safe-zone profiles are left untouched; hardware precedence with zones/DND and app/cloud/tracker round-trip behavior remain unverified under #41. Cloud readback is not proof that the physical tracker has applied a change. No automatic sound preview is played.

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

Options (Configure on the integration card): polling interval in seconds (default 60, minimum 10 — the vendor app polls every 10 s).

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
