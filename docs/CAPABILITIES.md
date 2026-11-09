# MyKi Spot — Capabilities map: Android app vs device/API vs Home Assistant

Sources: decompiled `com.allterco.mykispot` v2.6.19 and selected live API responses. The APK/decompiled artifacts are not shipped in this repository.
App code paths and stored cloud fields do not prove that every feature works on MyKi Spot hardware. Remaining app-parity verification is tracked in #29; this is not a support guarantee.

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
| `GET /api/watch/save-settings?key=safe_zone_N` | Extra key storage: `safe_zone_3` persisted; device enforcement and notifications remain unverified (experimental #31) | ❌ |

Auth: HTTP Basic (email:password) on `https://spot.myki.pet:6020/api/`. No tokens/sessions.
Related family backend (other Allterco devices, app `com.allterco.mykifamily`): `https://mj1-1.allterco.net:8020/japi` — different API, future work.

## 3. Comparison → Home Assistant mapping

| Capability | App | HA equivalent | Parity/better |
|---|---|---|---|
| Live position | map, 10 s | `device_tracker` (+ person, zones, map card) | = (60 s poll) |
| Safe zone state | colored marker | Zone sensor computed from the reported position and MyKi zones; no HA-zone synchronization | Automation input |
| Battery | icon | `sensor.battery` | = (+ automations) |
| Online | implicit | `binary_sensor.online` | = |
| Steps | fitness page | `sensor.steps_today` | = (+ history) |
| SOS / events | event list | `event.<name>_events`, polled; timestamp/rotation limitations apply | Not guaranteed or instant |
| Find (ring) | button | `button.find` / service | = |
| Force call | button | service | = |
| Position history | per-day view | HA recorder stores observed entity updates, not the full vendor track | Different coverage |
| Time-at-school stats | ❌ | `history_stats` sensor | **new** |
| Geofencing automations | fixed push only | any automation (calendar-aware) | **new** |
| Extra telemetry (GSM/sat/WiFi/speed) | ❌ | GSM, satellite, WiFi and tower sensors; supplemental tracker attributes | Additional telemetry |

## 4. Automation ideas (not preconfigured or hardware-verified)

Filter unknown/unavailable transitions and account for reporting and polling delays. Fresh cloud contact is not proof of a fresh position. These examples are not safety guarantees.

1. **School bell**: `sensor.child_zone` != "School" during school hours (workday/calendar condition) → notify parents.
2. **Arrived home**: kids' zone → Home → turn on hallway lights / stop alarm arming.
3. **Low battery**: < 20% → evening reminder to charge.
4. **SOS**: event `sos_alarm` → critical notification + optional camera snapshot / siren.
5. **Left home in the morning**: zone Home → Away on a school day before 08:30 → "on the bus" notification.
6. **Weekly report**: time at school / steps per day (history_stats + statistics).
7. **Actionable notification**: "The tracker is not reporting School — ring it?" → tap runs `myki.find`.
8. **Watch offline during school day** → maybe dead battery / forgot it.
