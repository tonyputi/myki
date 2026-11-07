# MyKi Spot — Capabilities map: Android app vs device/API vs Home Assistant

Sources: decompiled `com.allterco.mykispot` v2.6.19 (jadx, local `myki-re/`), live API test 2025-11-07.
This document is repo-ready (no secrets, no personal data).

## 1. What the Android app can do

### Account
- Register, login (email+password), logout, change password, delete account, forgot password (email + watch ID).

### Watches
- List watches on account, add watch, delete watch, rename / change watch phone number.

### Live map (per watch)
- Position with source type (GPS / WiFi / LBS) and accuracy; auto-refresh every 10 s.
- Battery level, online status, signal type.
- Safe zones (max 2) drawn on map; enter/exit push notifications.
- Real-time tracking mode (RTT): watch reports at high frequency for a configurable duration (default 10).

### History
- Daily GPS track (per day), events list (SOS alarm, low battery, safe zone in/out), step counter (today / per day / all).

### Watch configuration (remote commands)
- SOS numbers (3), whitelist (10), phonebook.
- Ring & call volumes, ringtone, sound profiles.
- DND / silence time (4 periods), alarms/reminders (3).
- LED on/off, mode, battery save mode, language, timezone.
- Pedometer on/off, walk time, sleep time, GPS on/off, report interval (e.g. 120 s), key lock, refuse unknown calls, center number, watch admin password.

### Actions
- Find watch (rings), force the watch to call a number, power off, restart, factory reset, test audio 1–4.

### Notifications (FCM push via notifications.allterco.com)
- Safe zone enter/exit, low battery, SOS.

## 2. What the device/API actually exposes (more than the app shows)

All `GET /api/watch/app-data?id=…` — raw telemetry the app mostly ignores:

| Field | Meaning | App uses it? |
|---|---|---|
| `current.position` lat/lon/accuracy/type | live fix (GPS/WiFi/LBS) | ✅ |
| `current.takenat` | fix timestamp | ✅ |
| `current.battery` | battery % | ✅ |
| `current.steps.todaySteps / allSteps` | fitness | ✅ |
| `current.gsmSignalStrength` | GSM signal % | ❌ |
| `current.gpsSatelites` | satellites in view | ❌ |
| `current.baseStations` | # cell towers seen | ❌ |
| `current.speed`, `current.direction` | movement | ❌ |
| `current.wifi[]` | nearby SSIDs w/ MAC + signal (mini wardrive) | ❌ |
| `current.flowers` | reward points | ❌ |
| `settings.safe_zone_1/2` | name/lat/lon/radius(km)/active/profile | ✅ |
| `settings.fw`, `mcc_mnc`, `msisdn`, `timezone` (incl. next DST change) | device info | partial |
| `settings.last_data_package`, `timestampUD` | last server contact | ❌ |
| `commands.*` | full device config (see app list above) | ✅ |
| `GET /api/watch/history/position?day=` | full daily track | ✅ |
| `GET /api/watch/history/events` | event log (`event_name`, `timestamp`) | ✅ |
| `GET /api/watch/history/steps` | step history | ✅ |
| `GET /api/watch/rtt?duration=` | real-time tracking window | ✅ |
| `GET /api/watch/save-settings?key=safe_zone_N` | **more than 2 safe zones** (verified live: `safe_zone_3` accepted and persisted; the app only shows 2) | ❌ |

Auth: HTTP Basic (email:password) on `https://spot.myki.pet:6020/api/`. No tokens/sessions.
Related family backend (other Allterco devices, app `com.allterco.mykifamily`): `https://mj1-1.allterco.net:8020/japi` — different API, future work.

## 3. Comparison → Home Assistant mapping

| Capability | App | HA equivalent | Parity/better |
|---|---|---|---|
| Live position | map, 10 s | `device_tracker` (+ person, zones, map card) | = (60 s poll) |
| Safe zone state | colored marker | `sensor.<name>` = Home/School/Away + HA zones | **better**: drives anything |
| Battery | icon | `sensor.battery` | = (+ automations) |
| Online | implicit | `binary_sensor.online` | = |
| Steps | fitness page | `sensor.steps_today` | = (+ history) |
| SOS / events | event list | `sensor.events` + instant notification automation | **better** |
| Find (ring) | button | `button.find` / service | = |
| Force call | button | service | = |
| Position history | per-day view | HA recorder (retention you choose) | **better** |
| Time-at-school stats | ❌ | `history_stats` sensor | **new** |
| Geofencing automations | fixed push only | any automation (calendar-aware) | **new** |
| Extra telemetry (GSM/sat/WiFi/speed) | ❌ | attributes | **new** |

## 4. Automations that make HA better than the app (the "figo" list)

1. **School bell**: `sensor.sofia_zone` != "School" during school hours (workday/calendar condition) → notify parents.
2. **Arrived home**: kids' zone → Home → turn on hallway lights / stop alarm arming.
3. **Low battery**: < 20% → evening reminder to charge.
4. **SOS**: event `sos_alarm` → critical notification + optional camera snapshot / siren.
5. **Left home in the morning**: zone Home → Away on a school day before 08:30 → "on the bus" notification.
6. **Weekly report**: time at school / steps per day (history_stats + statistics).
7. **Actionable notification**: "Sofia hasn't arrived at school — find her watch?" → tap runs `myki.find`.
8. **Watch offline during school day** → maybe dead battery / forgot it.
