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

## Extra details (verified later)

- Events (`watch/history/events`): items contain `event_name` + `timestamp`. Tests cover numeric timestamps; actual timestamp semantics and safe-zone event names still need vendor/hardware evidence. Startup history is not replayed.
- RTT (`watch/rtt?duration=`): the integration treats duration as minutes and sends the app default "10"; exact hardware timing remains to be verified.
- Live test 2025-11-07: 2 watches on account, full payload confirmed (wifi list, gsm signal, satellites, steps, timezone with next DST change, firmware).
- **MyKi Family app** (`com.allterco.mykifamily`, other Allterco devices) uses a different backend: `https://mj1-1.allterco.net:8020/japi` The analysis artifacts are not shipped here. Future work (#5).
