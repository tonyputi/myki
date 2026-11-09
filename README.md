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
| `device_tracker.<kid>` | Live GPS position (accuracy + battery) |
| `sensor.<kid>_zone` | The tracker's own safe zones: **"Home" / "School" / … / "Away"** |
| `sensor.<kid>_battery` | Battery % |
| `binary_sensor.<kid>_online` | Tracker online/offline |
| `sensor.<kid>_steps_today` | Today's step count |
| `event.<kid>_events` | SOS alarm / low battery / safe zone events (automation-ready) |
| `button.<kid>_live_tracking` | 10-minute live tracking window |
| `sensor.<kid>_live_tracking_seconds_left` | Live tracking countdown |
| `binary_sensor.<kid>_fresh_data` | Device has reported within 30 min |
| `sensor.<kid>_gsm_signal` | GSM signal % (diagnostic) |
| `button.<kid>_find` / `button.<kid>_call_me` | Ring the tracker / call you |
| `number.<kid>_ring_volume` / `number.<kid>_call_volume` | Volume sliders (config) |

The zone sensor is calculated from the reported position and active MyKi safe zones. Invalid coordinates or malformed zone configuration produce `unknown`, not `away`; disabled zones are ignored. Automations should ignore `unknown`/`unavailable` transitions and allow for tracker reporting and cloud polling delays.

**Services** (Developer Tools → Actions):

```yaml
# Make the tracker ring
action: myki.find
target:
  entity_id: device_tracker.jacopo

# Make the tracker call a number (use one from SOS/whitelist)
action: myki.make_call
target:
  entity_id: device_tracker.sofia
data:
  phone: "+35679060465"
```

## Attach a tracker to a person

The trackers work with HA people: **Settings → People → *your kid* → add the MyKi tracker**, next to the tablet's tracker. Home Assistant will use whichever source reported last — school hours covered by the tracker, home time by the tablet.

## Automation ideas

Event entities poll the vendor history and do not replay existing alarms when the integration loads. After history rotation, only events with numeric timestamps strictly newer than the last seen event are emitted; tied or unrecognized timestamps may be skipped. This is not a guaranteed or real-time safety notification system.

```yaml
# Not at school during school hours
alias: Sofia not at school
triggers:
  - trigger: time
    at: "08:45:00"
conditions:
  - condition: time
    after: "08:45:00"
    before: "13:00:00"
    weekday: [mon, tue, wed, thu, fri]
  - condition: state
    entity_id: sensor.sofia_zone
    state_not: School
actions:
  - action: notify.mobile_app_papa
    data:
      message: "Sofia non risulta a scuola"
```

- Kid left `Home` on a school morning → "on the bus" notification
- Battery < 20% → evening charge reminder
- Tracker offline on a school day → forgot/flat battery alert

More in [docs/CAPABILITIES.md](docs/CAPABILITIES.md).

## Installation

Requires **Home Assistant 2026.11.0 or newer**. Earlier releases are not supported.

**Marketplace (Home Assistant 2026.11+):** Settings → Marketplace → add `https://github.com/tonyputi/myki` as a custom repository (requires connecting your GitHub account once), then install **MyKi** — setup starts immediately, no restart needed.

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

The official `pytest-homeassistant==2026.11.0` package pins the tested HA version. CI uses the same requirements; no compatibility code for older HA versions is maintained.

## Supported devices

| Product | Type | Link | Status |
|---|---|---|---|
| **MyKi Spot** | GPS tracker | [mykifamily.com/myki-spot](https://mykifamily.com/myki-spot) | ✅ supported |
| MyKi Auto | GPS tracker | [mykifamily.com/myki-auto](https://mykifamily.com/myki-auto) | 🔀 same platform — untested |
| MyKi Touch | Watch | [mykifamily.com/myki-touch](https://mykifamily.com/myki-touch) | 🔀 same platform — untested |
| MyKi Watch 4 | Watch | [mykifamily.com/myki-watch](https://mykifamily.com/myki-watch) | 🔀 same platform — untested |
| MyKi Watch 4 Lite | Watch | [mykifamily.com/myki-watch-4-lite](https://mykifamily.com/myki-watch-4-lite) | 🔀 same platform — untested |

The integration identifies known models from the device firmware. Diagnostics contain only anonymous model, battery, signal, step and online status, plus account polling status; raw vendor payloads, identifiers, contacts and locations are not exported. For model-identification issues, report the model and firmware version shown on the device page, without sharing personal data.

## Trademark

MyKi and the MyKi logo are trademarks of Allterco Consulting Ltd.
The icon used in this README is the official MyKi asset from mykifamily.com.

## License

[MIT](LICENSE)
