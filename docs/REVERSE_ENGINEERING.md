# MyKi reverse engineering notes

The integration uses the MyKi Spot Android app API (v2.6.19, `com.allterco.mykispot`). These notes combine decompiled code paths with selected live API responses; listing an endpoint does not prove that its behavior has been verified on hardware.


## Server & auth

- **Base URL:** `https://spot.myki.pet:6020/api/`
- **Auth:** plain **HTTP Basic** — `Authorization: Basic base64(email:password)`. Same static header on every call; no tokens, no sessions, no signing (confirmed in `LoginActivity.signIn` + `Token.kt`). Verified live: unauthenticated calls return `401 {"isok":false,"err":"unauthorized"}`.
- The app polls every **10 s** (`MainMapFragment` timer) — no websocket/MQTT/push for position data. Push (FCM via `https://notifications.allterco.com/pet/user/`) is only for notifications, not needed for HA.
- Response envelope: `{"isok": true/false, "data": {...}, "err": ...}`.

## Endpoints relevant to Home Assistant

| What | Call |
|---|---|
| List trackers | `GET /api/watch` → `data.allw[] = {id, nickname}` |
| Full state | `GET /api/watch/app-data?id=<id>` |
| History track | `GET /api/watch/history/position?id=<id>&day=YYYY-MM-DD` |
| Events | `GET /api/watch/history/events?id=<id>` |
| Steps | `GET /api/watch/history/steps?id=<id>[&day=YYYY-MM-DD]` |
| Find watch (ring) | `GET /api/watch/find?id=<id>` |
| Real-time tracking | `GET /api/watch/rtt?id=<id>&duration=<duration>` |

Commands also available (not needed for presence): `watch/call`, `watch/sos`, `watch/whitelist`, `watch/save-settings?key=&val=`, `watch/profile`, `watch/led`, `watch/mode`, `watch/poweroff`, `watch/reset`, `watch/factory`, `watch/silencetime`, `watch/remind`, `watch/ringvolset`, `watch/callvolset`, `watch/ringtone`, `user/edit`, `user/delete`, `reset/password`.

## `watch/app-data` JSON shape (parsed in `TrackerInformationHandler.kt`)

```json
{
  "isok": true,
  "data": {
    "current": {
      "position": {"latitude": "45.12", "longitude": "9.34", "accuracy": "20"},
      "battery": "85",
      "RTT_secondsLeft": "0",
      "takenat": "2025-11-07 12:00:00"
    },
    "settings": {
      "online": "1",
      "msisdn": "+15555550100",
      "nickname": "Example tracker",
      "battery_save_mode": "...",
      "safe_zone_1": "{\"name\":\"Home\",\"lat\":10.0,\"lon\":20.0,\"radius\":0.15,\"active\":1,\"profile\":1}",
      "safe_zone_2": "{\"name\":\"School\",...}",
      "mode": "..."
    },
    "commands": {
      "silencetime": "00:00-00:00,00:00-00:00,00:00-00:00,00:00-00:00",
      "remind": "...", "volume_ring": "...", "ringtone": "...",
      "led": "...", "volume_call": "...",
      "sos_phone_1..3": "...", "whitelist_1..2": "..."
    }
  }
}
```

Notes: values are strings; `takenat` is watch-local time; `safe_zone_N` is a JSON string inside a string, **radius in km** (app stores meters ÷ 1000, confirmed in `SafeZonesFragment`); DND "all zeros" pattern means off.

## Contact slot evidence

Static inspection of the operator-supplied installed APK, version `2.6.19.8a84c06` (version code `2025082601`), SHA-256 `7196ce4e66dc4924da966e30645597a27b4538353f6fc3771ba9aca2b676eca2`:

- `ApiInterface.addSosNumber`: `GET watch/sos?id=&num=1..3&phone=` writes an individual SOS slot.
- `ApiInterface.addWhitelistNumbers`: `GET watch/whitelist?id=&whitelist=1..2&phone1=&phone2=&phone3=&phone4=&phone5=` writes one complete five-slot group, including empty values.
- `TrackerInformationHandler.getTrackerInformation` reads `commands.sos_phone_1..3` and comma-separated `commands.whitelist_1..2`.
- `TrackerInformation.getWhitelistFirstFive/getWhitelistSecondFive` split the groups by comma, preserving positional slots; an empty group is treated as five blanks.
- `SosAndWhitelistFragment.setPhoneNumbersToEditTexts/makeChanges` exposes three SOS and seven whitelist fields. The app sends whitelist 1 as five numbers and whitelist 2 as two numbers followed by three blanks. HA deliberately preserves all five existing entries instead of copying that destructive behavior.
- `addSosNumber/addWhiteListNumbers/getContactPhone` convert `+` to `00` and strip non-digits. HA accepts only digits with an optional leading `+`, rejecting malformed input instead of silently deleting characters. Equivalent `+`/`00` values compare equally without guessing a country prefix.
- The phonebook buttons use Android `ACTION_PICK` with the phone contact MIME type; the fragment stores numbers, not contact names.

Analysis used the existing JADX CLI, not REA Evidence: REA's Android provider was unavailable because `REA_JADX_MCP_JAR` was not configured. The full decompilation reported 119 errors elsewhere; the contact fragment's write/read methods and API declarations above were available as Java output. No APK execution, app storage extraction, credential access or live contact write was performed. Static declarations establish the app protocol, not server acceptance or hardware application; the physical round-trip remains an explicit #27 verification task.

The API exposes no conditional-write revision in these declarations. Local HA serialization cannot guarantee atomic conflict prevention against simultaneous app edits; read-before-write and readback reduce, but cannot eliminate, that race.

## Settings and notification scope evidence

The following observations use the same APK/hash and JADX limitations as the contact inspection above. They are static evidence, not live execution:

- `PersonalizeFragment.setRightView` reads global profile **1 sound+vibration, 2 sound, 3 vibration, 4 mute** and ringtone **0 Classic, 1 Playtime, 2 Twinkle**. Its setters call `watch/profile` and `watch/ringtone` separately. `TrackerInformationHandler` populates the corresponding model from command state.
- `SafeZonesFragment.setValuesToControllersAndDrawZone` maps zone `profile` 1–4 to those sound/vibration buttons. `addSafeZone` serializes only `name`, `lat`, `lon`, `radius`, `active`, `profile`. This establishes a per-zone sound profile, **not a per-zone ringtone/melody** or proven device-side switching/exit behavior.
- `SettingsFragment.bakeSpaghettiCombinationForNotificationAndRegister` builds push permission bits from SOS, low battery, zone out and zone in switches, invokes the FCM registration helper, and saves a separate preference string in Android storage. `setSwitchesToRightPosition` reloads that local string. `NotificationsHandler.registerFCM` submits the bits with FCM token, Firebase installation ID and account tracker IDs to the notification backend. No read/write of a shared tracker setting is established by this path; remote control of an existing phone's registration is not established either.
- `DialogBatterySaveModeFragment.batterySaveMode` uses `watch/save-settings` with key `battery_save_mode` and values 0/1. `DeviceModeFromSettingsFragment` uses `ChooseFunctionalityActivity` constants `sos`, `pet`, `asset` and calls `watch/mode`. Firmware effects and mode side effects require separate verification.
- `DNDFragment.bakePeriod` serializes a start/end wall-clock interval as `HH:MM-HH:MM`. `setDND` sends it as period 1 (or the zero sentinel when disabled), followed by three zero periods. This is not evidence of correct overnight/DST handling, and HA must not copy the app's clearing of other periods blindly.
- `Alarm` exposes time, active state and seven weekday bits from its serialized alarm string. `AlarmSetFragment` and `AlarmsListFragment` write three alarm values together using `watch/remind`; weekday order and disabled forms must be verified before implementation.
- `PersonalizeFragment` maps the status-light switch through `HomeActivity` LED operations. `HomeActivity` distinguishes default=1, off=0, temporary on/party=2. A binary switch must not conflate all three semantics without verification.
- The app force-call dialog submits the entered phone directly through `watch/call`. The HA Call contact selector is a convenience for initiating that command, not a vendor setting or emergency-contact ordering control. The app's ordered SOS slots do not prove firmware dialing fallback/retry behavior.

Implementation dispositions and focused tracking issues are maintained in [CAPABILITIES.md](CAPABILITIES.md), parent #29. Dangerous endpoint declarations are inventory only, never execution approval.

## Extra details (verified later)

- Events (`watch/history/events`): items contain `event_name` + `timestamp`. Tests cover numeric timestamps; actual timestamp semantics and safe-zone event names still need vendor/hardware evidence. Startup history is not replayed.
- RTT (`watch/rtt?duration=`): the integration treats duration as minutes and sends the app default "10"; exact hardware timing remains to be verified.
- Live test 2025-11-07: 2 watches on account, full payload confirmed (wifi list, gsm signal, satellites, steps, timezone with next DST change, firmware).
- **MyKi Family app** (`com.allterco.mykifamily`, other Allterco devices) uses a different backend: `https://mj1-1.allterco.net:8020/japi` The analysis artifacts are not shipped here. Future work (#5).
