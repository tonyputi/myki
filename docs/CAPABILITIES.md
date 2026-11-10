# MyKi Spot — Capabilities map: Android app vs device/API vs Home Assistant

Sources: decompiled `com.allterco.mykispot` v2.6.19 and selected live API responses. The APK/decompiled artifacts are not shipped in this repository.
App code paths and stored cloud fields do not prove that every feature works on MyKi Spot hardware. Remaining app-parity verification is tracked in #29; this is not a support guarantee.

This inventory uses the operator's screen walkthrough and static code from APK `2.6.19.8a84c06` (artifact hash and analysis limitations in [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md)). Screenshots and remaining screen-by-screen validation are still pending. HA status below describes the current implementation, not proof that every control has been physically tested. A one-to-one inventory means every app capability gets a disposition, not that destructive or phone-local controls must become HA entities.

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

| App capability | HA status / intended disposition | Evidence and tracking |
|---|---|---|
| Tracker list and per-tracker live map | Implemented: one HA device and `device_tracker` per tracker; polling defaults to 60 s, not the app's 10 s | `MainMapFragment`, integration coordinator; no custom replica of the app map |
| Battery, online status, current steps | Implemented sensors; hardware reporting delay still applies | `TrackerInformationHandler`, integration sensor platforms |
| Two safe zones: name, coordinates, radius, enabled state | Partial: computed zone sensor exists; shared zone editing is missing | `SafeZonesFragment`, #28 |
| Sound/vibration profile per safe zone | Missing: profile 1–4 is stored inside each zone; not a per-zone melody | `SafeZonesFragment.addSafeZone/setValuesToControllersAndDrawZone`, #28 |
| SOS numbers 1–3 | Implemented shared text slots; physical round-trip remains pending | `SosAndWhitelistFragment`, #27 / merged #40 |
| Whitelist numbers 1–7 | Implemented shared text slots; preserve all ten cloud positions, including hidden 8–10 | Same sources and #27; do not erase hidden slots |
| Android phonebook picker | App imports a phone number; not a second named cloud contact book | `SosAndWhitelistFragment.getContactPhone`, #27 |
| Physical SOS button dialing | Ordered slots are preserved, but exact dialing order/fallback/retry behavior is not established by app code or the user's single observed first-number call | #27; do not test emergency calls without explicit approval |
| App command to make tracker call a number | Implemented `myki.make_call`; HA resolves an existing shared slot | `DialogAskForPhoneNumberToCallFragment`, #27 |
| HA Call contact selector / Call me button | Removed: no equivalent shared MyKi setting; saved local options and registry entries are cleaned up without cloud writes | #27; explicit `myki.make_call` action remains, with a target supplied per execution |
| Find tracker | Implemented button and entity action | `ApiInterface.findTracker`, integration button/tracker platforms |
| Live tracking / RTT | Implemented command and countdown; exact duration units and limits remain unverified | `ApiInterface.startRealTimeTracking`, #29 |
| Ring volume and call volume | Implemented number entities; retain existing IDs and readback behavior | `PersonalizeFragment`, #41 |
| Global ring mode: sound+vibration / sound / vibration / mute | Implemented cloud-backed selector; app profile values 1/2/3/4, no saved HA preference | `PersonalizeFragment.setRightView/changeSoundProfile`, #41 |
| Global ringtone: Classic / Playtime / Twinkle | Implemented cloud-backed selector; app values 0/1/2 | `PersonalizeFragment.setRightView/setRingtone`, #41 |
| Status LED switch | Implemented: default=1, disabled=0; temporary party=2 reads unknown and is never sent by the switch | `PersonalizeFragment`, `HomeActivity` LED constants, #41 |
| Battery save | Missing shared control; app writes `battery_save_mode` 0/1 | `DialogBatterySaveModeFragment.batterySaveMode`, #42 |
| SOS Button / Pet Tracker / Asset Tracker mode | Partial: mode attribute exists, shared editing missing; these modes are not different product models | `DeviceModeFromSettingsFragment`, `ChooseFunctionalityActivity`, #42 |
| Do not disturb: enabled, start and end time | Missing; app edits one HH:MM-HH:MM period while API accepts four | `DNDFragment`, #43 |
| Alarms 1–3: enabled, time, weekdays | Missing; grouped writes must preserve other alarm slots | `Alarm`, `AlarmSetFragment`, `AlarmsListFragment`, #43 |
| Notifications: Zone in | Phone-push preference, not a verified tracker switch; HA computed zone transitions differ | `SettingsFragment`, `NotificationsHandler`, #44; HA example #30 |
| Notifications: Zone out | Same phone-registration scope; no claim of HA↔phone preference synchronization | Same sources, #44 |
| Notifications: Low battery | Same phone-registration scope; HA battery sensor/event exists, automatic phone notification parity does not | Same sources, #44 |
| Notifications: SOS pressed | Same phone-registration scope; HA polls retained events, not guaranteed real-time push | Same sources, #44 |
| Power off | Not exposed; decide safety/recovery before implementation | `TrackerSettingsFragment`, `ApiInterface`, #45 |
| Restart | Not exposed; distinguish restart from factory reset and establish retained settings | Same sources, #45 |
| Factory reset | Not exposed; destructive, explicit scope/approval required | Same sources, #45 |
| Delete device from MyKi account | Not exposed; different from removing an HA integration or resetting hardware | Same sources, #45 |
| Rename tracker / edit tracker SIM number | Missing shared editing; HA entity/device rename alone does not update MyKi | `ApiInterface.changeTrackerNameOrPhone`; disposition pending under #29 |
| Add/register tracker | App-managed provisioning for now; HA discovers account trackers at setup/reload, dynamic-add behavior needs review | `ApiInterface.addNewTrackerToAccount`, #29 |
| Daily position track history | Partial: HA Recorder only stores observed entity updates, not the complete vendor daily track | `ApiInterface.getTrackerHistoryPosition`, #29 |
| Daily/all step history and retained event list UI | Partial: current steps/event entities exist; no replica of the vendor historical browsing UI | `ApiInterface`, #29; event timestamps/rotation remain bounded |
| Register account, change/reset password, delete account | Account management stays app-managed pending explicit scope; HA login/reauth is not account administration | Account API declarations; #29, separate from device deletion #45 |
| App language, tooltips, map style and local profile image | Phone/HA frontend presentation, not assumed shared tracker configuration | `SettingsFragment`, `ProfileImageHandler`; #29 classification review |

### Evidence gates and exclusions

- MyKi cloud is the source of truth for contacts and tracker settings; do not invent persistent HA-only tracker preferences. Integration-only connection/polling settings are separate. The code preserves SOS slot positions; it does **not** establish the tracker's full emergency dialing algorithm. Removing the HA-only calling selector/button does not change physical SOS behavior.
- Global personalization controls require fresh cloud data and confirmed readback, reject stale/offline writes and do not alter safe-zone JSON. Physical behavior and precedence with zones/DND remain unverified under #41.
- Zone `profile` values mean **1 sound+vibration, 2 sound, 3 vibration, 4 mute** in app read/write code. Zone JSON contains no ringtone selection in that path. Global ringtone selection is separate. Physical switching on entering/leaving a zone, precedence with DND/global mode and restoration on exit require hardware evidence; do not promise them based on storage alone.
- Notification preferences are loaded from Android storage and registered with FCM tokens/installation IDs. Do not imitate the phone or collect its tokens to create apparent parity. #44 must decide what can actually be synchronized and document phone-local exclusions.
- The operator reports a satellite count of zero. HA exposes the vendor value without substituting zero for missing data. Compare a recent GPS fix against the cloud before diagnosing it; exact satellite semantics remain unverified under #29.
- Metadata-only/API-only candidates, hidden cloud slots, extra safe zones (#31), app debug/test audio commands and other backends (#5) are not automatically approved Spot UI features.
- Account/provisioning/history/UI rows still need a screen-by-screen disposition review under #29. This initial matrix is not a claim that all app screens, mode-dependent controls or hardware effects have been exhaustively verified.

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
