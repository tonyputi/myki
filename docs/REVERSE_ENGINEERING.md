# MyKi reverse engineering notes

How the integration talks to the cloud: everything below was derived from the official Android app (v2.6.19, `com.allterco.mykispot`) and verified with live API calls.


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
| Real-time tracking | `GET /api/watch/rtt?id=<id>&duration=<sec>` |

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
      "msisdn": "+39...",
      "nickname": "Nome",
      "battery_save_mode": "...",
      "safe_zone_1": "{\"name\":\"Casa\",\"lat\":45.1,\"lon\":9.3,\"radius\":150,\"active\":1,\"profile\":1}",
      "safe_zone_2": "{\"name\":\"Scuola\",...}",
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

## Extra details (verified later)

- Events (`watch/history/events`): items have `event_name` + `timestamp`; known types: `sos_alarm`, `low_battery`, safe zone in/out.
- RTT (`watch/rtt?duration=`): duration in minutes, app default "10".
- Live test 2025-11-07: 2 watches on account, full payload confirmed (wifi list, gsm signal, satellites, steps, timezone with next DST change, firmware).
- **MyKi Family app** (`com.allterco.mykifamily`, other Allterco devices) uses a different backend: `https://mj1-1.allterco.net:8020/japi` (see `myki-re/family/`). Future work.
