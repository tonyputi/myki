# MyKi Spot — Capabilities map: Android app vs device/API vs Home Assistant

Sources: decompiled `com.allterco.mykispot` v2.6.19 and selected live API responses. The APK/decompiled artifacts are not shipped in this repository.
App code paths and stored cloud fields do not prove that every feature works on MyKi Spot hardware. The historical inventory is #29; remaining physical checks are grouped in the README final acceptance checklist and existing settings issues. This is not a support guarantee.

This inventory uses the operator's screen walkthrough and static code from APK `2.6.19.8a84c06` (artifact hash and analysis limitations in [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md)). Eleven operator-supplied screenshots were inspected locally (tracker settings, personalization, modes, DND, contacts, both safe zones, quick settings, history and app settings). Private images and their account/contact/location data are not published. Remaining physical validation is grouped into the final acceptance session described in README. HA status below describes the current implementation, not proof that every control has been physically tested. A one-to-one inventory means every app capability gets a disposition, not that destructive or phone-local controls must become HA entities.

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
- SOS numbers (3) and app-visible whitelist numbers (7). The cloud stores two five-entry whitelist groups; the app does not expose the last three entries. The phonebook icon imports a number from Android contacts, not a separate named cloud address book.
- Ring & call volumes, ringtone, sound profiles.
- DND enable/start/end time: the app edits one period; the API accepts four periods. Device timezone, overnight behavior and preservation of additional periods require verification.
- Three alarms with time, enabled state and weekday selection.
- Status LED, SOS/Pet/Asset operating mode and battery save mode.
- Language is also an app setting; do not assume that changing Android UI language changes tracker firmware language.

Other previously listed fields (pedometer enable, walk/sleep time, GPS enable, report interval, key lock, unknown-call refusal, center number, admin password and timezone editing) are **not established as user-facing Spot controls by this walkthrough**. Keep them as unverified protocol/field candidates under #29, not promised app parity or an automatic implementation backlog.

### Actions
- Find watch (rings), force the watch to call a number, power off, restart, factory reset, test audio 1–4.

### Notifications (FCM push via notifications.allterco.com)
- Four switches: Zone in, Zone out, Low battery and SOS pressed.
- The examined app stores their selection in Android preferences and submits permission bits with its phone FCM registration. These are not established as shared tracker settings or account-global preferences. HA event processing and HA notifications are a separate mechanism (#44).

## 2. What the device/API actually exposes (more than the app shows)

All `GET /api/watch/app-data?id=…` — raw telemetry the app mostly ignores:

| Field | Meaning | App uses it? |
|---|---|---|
| `current.position` lat/lon/accuracy/type | live fix (GPS/WiFi/LBS) | ✅ |
| `current.takenat` | fix timestamp | ✅ |
| `current.battery` | battery % | ✅ |
| `current.steps.todaySteps / allSteps` | fitness | ✅ |
| `current.gsmSignalStrength` | GSM signal % | ❌ |
| `current.gpsSatelites` | Vendor satellite count; exact used/visible semantics unverified | ❌ |
| `current.baseStations` | # cell towers seen | ❌ |
| `current.speed`, `current.direction` | movement | ❌ |
| `current.wifi[]` | nearby SSIDs w/ MAC + signal (mini wardrive) | ❌ |
| `current.flowers` | reward points | ❌ |
| `settings.safe_zone_1/2` | name/lat/lon/radius(km)/active/profile | ✅ |
| `settings.fw`, `mcc_mnc`, `msisdn`, `timezone` (incl. next DST change) | device info | partial |
| `settings.last_data_package`, `timestampUD` | last server contact | ❌ |
| `commands.*` | Command-state fields; UI usage and hardware semantics must be checked per field | partial |
| `GET /api/watch/history/position?day=` | full daily track | ✅ |
| `GET /api/watch/history/events` | event log (`event_name`, `timestamp`) | ✅ |
| `GET /api/watch/history/steps` | step history | ✅ |
| `GET /api/watch/rtt?duration=` | real-time tracking window | ✅ |
| `GET /api/watch/save-settings?key=safe_zone_N` | Extra key storage: `safe_zone_3` persisted; device enforcement and notifications remain unverified (experimental #31) | ❌ |

Auth: HTTP Basic (email:password) on `https://spot.myki.pet:6020/api/`. No tokens/sessions.
Related family backend (other Allterco devices, app `com.allterco.mykifamily`): `https://mj1-1.allterco.net:8020/japi` — different API, future work.

## 3. App → Home Assistant disposition matrix

**Implemented** means code/tests exist; **partial** means coverage differs; **missing** means no shared control yet; **decision** means scope or safety must be settled, not silently omitted. Every future cloud control must preserve other settings, display confirmed readback and report failures without exposing personal data.

All tracker settings are available from **MyKi → Configure → Tracker settings**, using one selected tracker and native sections for contacts, audio/LED, device/battery, map-based zones and schedules. Forms read fresh cloud values and save only on submission; HA options store no tracker preferences. The old editable device-page entities are disabled on migration and by default for new entries, with IDs retained for explicit compatibility opt-in. Status/diagnostic entities and quick commands remain on the device page.

| App capability | HA status / intended disposition | Evidence and tracking |
|---|---|---|
| Tracker list and per-tracker live map | Implemented: one HA device and `device_tracker` per tracker; polling defaults to 60 s, not the app's 10 s | `MainMapFragment`, integration coordinator; no custom replica of the app map |
| Battery, online status, current steps | Implemented sensors; hardware reporting delay still applies | `TrackerInformationHandler`, integration sensor platforms |
| Two safe zones: name, coordinates, radius, enabled state | Implemented: native map/radius configuration form, computed zone sensor, cloud summary sensors and structured `myki.set_safe_zone` action; preserves unknown fields and other slots | `SafeZonesFragment`, #28 |
| Sound/vibration profile per safe zone | Implemented through `myki.set_safe_zone` ring_mode 1–4; not a per-zone melody | `SafeZonesFragment.addSafeZone/setValuesToControllersAndDrawZone`, #28 |
| SOS numbers 1–3 | Implemented shared contact editor; physical round-trip remains pending | `SosAndWhitelistFragment`, #27 / merged #40 |
| Whitelist numbers 1–7 | Implemented shared contact editor; preserve all ten cloud positions, including hidden 8–10 | Same sources and #27; do not erase hidden slots |
| Android phonebook picker | App imports a phone number; not a second named cloud contact book | `SosAndWhitelistFragment.getContactPhone`, #27 |
| Physical SOS button dialing | Ordered slots are preserved. Screenshot help says holding SOS more than 6 seconds starts sequential calls to the SOS list; firmware fallback/retry and successful physical dialing remain unverified | #27; do not test emergency calls without explicit approval |
| App command to make tracker call a number | Implemented `myki.make_call`; HA resolves an existing shared slot | `DialogAskForPhoneNumberToCallFragment`, #27 |
| HA Call contact selector / Call me button | Removed: no equivalent shared MyKi setting; saved local options and registry entries are cleaned up without cloud writes | #27; explicit `myki.make_call` action remains, with a target supplied per execution |
| Find tracker | Implemented button and entity action | `ApiInterface.findTracker`, integration button/tracker platforms |
| Live tracking / RTT | Implemented command and countdown; exact duration units and limits remain unverified | `ApiInterface.startRealTimeTracking`, #29 |
| Ring volume and call volume | Implemented native volume editor with stale/offline checks, serialized writes and confirmed readback; legacy number IDs retained but disabled by default | `PersonalizeFragment`, #41 |
| Global ring mode: sound+vibration / sound / vibration / mute | Implemented native cloud-backed editor; app profile values 1/2/3/4, no saved HA preference | `PersonalizeFragment.setRightView/changeSoundProfile`, #41 |
| Global ringtone: Classic / Playtime / Twinkle | Implemented native cloud-backed editor; app values 0/1/2; absent cloud field uses the app's Classic initial value | `PersonalizeFragment.setRightView/setRingtone`, #41 |
| Status LED switch | Implemented native editor: default=1, disabled=0; temporary party=2 leaves the choice unselected and is never offered as a status preference | `PersonalizeFragment`, `HomeActivity` LED constants, #41 |
| Flashlight | Implemented separate switch: temporary LED=2; off restores default=1, without locally remembering a prior preference | `HomeActivity` quick-settings handler; physical effects unverified |
| Battery save | Implemented native cloud-backed editor; app writes `battery_save_mode` 0/1 | `DialogBatterySaveModeFragment.batterySaveMode`, #42 |
| SOS Button / Pet Tracker / Asset Tracker mode | Implemented native cloud-backed mode editor with readback and unexpected known-configuration-change detection; not hardware models | `DeviceModeFromSettingsFragment`, `ChooseFunctionalityActivity`, #42 |
| Do not disturb: enabled, start and end time | Implemented native time editor, summary sensor and `myki.set_dnd`; edits period 1, preserves the other three; tracker wall-clock times without HA timezone conversion | `DNDFragment`, #43 |
| Alarms 1–3: enabled, time, weekdays | Implemented native time/weekday editor, summary sensors and `myki.set_alarm`; preserves fresh sibling slots and opaque alarm digit; Sunday-first app weekday order | `Alarm`, `AlarmSetFragment`, `AlarmsListFragment`, #43 |
| Notifications: Zone in | App-only phone-push preference, not a shared tracker switch; HA computed zone transitions differ | `SettingsFragment`, `NotificationsHandler`, #44; HA example #30 |
| Notifications: Zone out | App-only phone-registration scope; no HA↔phone preference synchronization | Same sources, #44 |
| Notifications: Low battery | App-only phone-registration scope; HA battery sensor/event exists, automatic phone notification parity does not | Same sources, #44 |
| Notifications: SOS pressed | App-only phone-registration scope; HA polls retained events, not guaranteed real-time push | Same sources, #44 |
| Power off | Explicit `myki.power_off` action, requires confirm=true; no ordinary button, known remote wake or promise of completed shutdown; physical recovery required | `TrackerSettingsFragment`, `ApiInterface`, #45 |
| Restart | Explicit `myki.restart` action using watch/reset, requires confirm=true; cloud acceptance only, interruption and configuration retention remain physical checks | Same sources, #45 |
| Factory reset | Deliberately app-only: potential configuration loss/re-pairing, recovery not sufficiently established; no HA endpoint/action | Same sources, #45 |
| Delete device from MyKi account | Deliberately app-only: account unlinking/loss of tracking; recovery unknown and distinct from HA removal or hardware reset | Same sources, #45 |
| Rename tracker / edit tracker SIM number | Implemented native shared metadata editor; paired write preserves the fresh other field, rejects stale/offline edits and requires readback. Does not reprogram the SIM or overwrite HA custom names | `TrackerSettingsFragment.changeNameOrPhoneOfTracker`, `ApiInterface.changeTrackerNameOrPhone` |
| Add/register tracker | App-managed provisioning for now; HA discovers account trackers at setup/reload, dynamic-add behavior needs review | `ApiInterface.addNewTrackerToAccount`, #29 |
| Daily position track history | Partial: HA Recorder only stores observed entity updates, not the complete vendor daily track | `ApiInterface.getTrackerHistoryPosition`, #29 |
| Daily/all step history and retained event list UI | Partial: current steps/event entities exist; no replica of the vendor historical browsing UI | `ApiInterface`, #29; event timestamps/rotation remain bounded |
| Register account, change/reset password, delete account | Account management stays app-managed pending explicit scope; HA login/reauth is not account administration | Account API declarations; #29, separate from device deletion #45 |
| App language, tooltips, map style and local profile image | Phone/HA frontend presentation, not shared tracker configuration; safe-zone colors are also phone-local in the examined write path | `SettingsFragment`, `ProfileImageHandler`; #29 classification review |

### Evidence gates and exclusions

- MyKi cloud is the source of truth for contacts and tracker settings; do not invent persistent HA-only tracker preferences. Integration-only connection/polling settings are separate. The code preserves SOS slot positions; it does **not** establish the tracker's full emergency dialing algorithm. Removing the HA-only calling selector/button does not change physical SOS behavior.
- Global personalization controls require fresh cloud data and confirmed readback, reject stale/offline writes and do not alter safe-zone JSON. Physical behavior and precedence with zones/DND remain unverified under #41.
- Zone `profile` values mean **1 sound+vibration, 2 sound, 3 vibration, 4 mute** in app read/write code. Zone JSON contains no ringtone selection in that path. Global ringtone selection is separate. Physical switching on entering/leaving a zone, precedence with DND/global mode and restoration on exit require hardware evidence; do not promise them based on storage alone.
- Notification preferences are loaded from Android storage and registered with FCM tokens/installation IDs. Do not imitate the phone or collect its tokens to create apparent parity. The examined API interface offers no supported read/edit route for an existing phone registration without its private registration identity. Remote synchronization is therefore not exposed; this bounded code inspection is not a claim that no other vendor API exists.
- The operator reports a satellite count of zero. HA exposes the vendor value without substituting zero for missing data. Compare a recent GPS fix against the cloud before diagnosing it; exact satellite semantics remain unverified under #29.
- Metadata-only/API-only candidates, hidden cloud slots, extra safe zones (#31), app debug/test audio commands and other backends (#5) are not automatically approved Spot UI features.
- Account/provisioning and full historical browsing remain app-managed; phone-local presentation belongs to the app or HA frontend. This batch implements shared Spot controls, not a replica app, another backend or destructive account administration. Mode-dependent controls and hardware effects still need final acceptance.
- Grouped configuration actions preserve cloud siblings/unknown fields, reject stale/offline/malformed edits and require readback. No local defaults, retries or rollback after uncertainty. Mode changes can have device-side side effects; detecting unexpected cloud configuration changes does not prevent them.
- Power actions require explicit per-execution confirmation, but no custom HA confirmation dialog or recovery guarantee is promised. Factory reset/deletion have a documented app-only disposition; no live destructive tests are needed to complete that decision.

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
