# MyKi — Sponsorship Plan

Sponsorship strategy for the MyKi Home Assistant integration (github.com/tonyputi/myki,
first device: MyKi Spot kids GPS watch by Allterco).

## Positioning

MyKi is a free, open-source HACS integration built by a parent for parents: it brings
Allterco MyKi kids GPS watches into Home Assistant so location, battery, and alerts live
next to everything else in the home. The ask mirrors what works for comparable HA authors
(petlibro, tr4nt0r, maykar): a human, one-sentence appeal — "if MyKi saved you from
another vendor app, help keep it maintained" — placed at moments of value (release notes,
resolved issues, README), never a paywall. Every feature stays free for every family;
sponsors get convenience (early releases, priority triage) and a vote on the next device,
not locked functionality.

## Launch checklist

Do these before announcing anywhere:

- [ ] GitHub Sponsors profile: both Italy and Malta are Stripe-supported payout regions;
      connect bank account, complete tax interview (no platform fee — GitHub covers
      payment processing).
- [ ] Sponsors profile text: lead with MyKi ("custom Home Assistant integration for MyKi
      kids GPS watches, installed by N families"), one-sentence ask, photo of the actual
      use case (watch on a kid's wrist next to an HA dashboard).
- [ ] `.github/FUNDING.yml` in the repo root with `github: tonyputi` — enables the
      native **Sponsor** button on the repository.
- [ ] README badge near the title: shields.io GitHub Sponsors badge
      (`https://img.shields.io/github/sponsors/tonyputi`) + a short "Support the project"
      section at the bottom (one line + link, no guilt copy).
- [ ] Issue templates and Discussions: single neutral line "This project is maintained
      in spare time; sponsorship keeps it alive" with sponsor link.
- [ ] Release notes template: one sponsor line per release, nothing more.

## Tiers

GitHub Sponsors supports monthly and one-time tiers; amounts below in EUR
(Sponsors converts for the payer). Keep the ladder small — parents, not companies.

| Tier | Amount | What sponsors get |
|------|--------|-------------------|
| Thanks (one-time) | €5 | Thank-you in the next release notes |
| Family pack (one-time) | €15 | Above + name in README backers list |
| Supporter (monthly) | €3 | Backers list + sponsor label on issues |
| Family (monthly) | €8 | Above + **beta channel**: pre-release tags HACS exposes via "show beta" — new devices and fixes land there days early |
| Champion (monthly) | €20 | Above + **priority triage**: issues labeled within 72h, looked at first + one vote per roadmap poll (next device, next feature) |

Deliverables cost nothing to run: beta = GitHub pre-releases, triage = a `sponsor`
label and response habit, votes = a GitHub Discussion poll. Never gate core features.

## Channels

| Channel | Action |
|---------|--------|
| HACS default catalog | The real growth channel. Meet repo requirements (single integration under `custom_components/myki/`, `hacs.json`, README, tagged releases), then submit the PR to hacs/default. Being in the default list is what made peers' numbers. |
| HA community forum | Post in *Share your Projects! → Custom Integrations* with a demo GIF. Also answer existing GPS-watch threads (SeTracker/Xplora requests exist and go unanswered) pointing to MyKi as the solution. |
| r/homeassistant (~600k members) | Personal project posts are allowed (ads are not). Post as a build story: problem (vendor app), reverse-engineering, result. Reply in any kids-watch/GPS-tracker thread that surfaces. |
| Italian HA groups | Home Assistant Italia Facebook group + Italian HA Telegram/Discord groups: same build-story post, in Italian. Primary audience — MyKi sells in Italy. |
| Malta | Local maker/tech groups and HA Malta contacts; Allterco is Bulgarian with strong Malta presence — same company as Shelly, an angle Shelly-using HA folks recognize. |
| MyKi parent communities | Facebook groups where MyKi-watch parents already complain about the vendor app. Soft approach only: answer real questions (battery, alerts, geofence), link the integration where it genuinely solves the thread. |

## 90-day plan

**Days 0–15 — foundation.** Ship v1.0, complete the launch checklist, submit HACS
default PR, forum post, r/homeassistant post, Italian-groups post.
Metrics: 50+ GitHub stars, listed in HACS, 50–100 active installs (HA analytics
undercounts; treat as a floor), first issue from a stranger.

**Days 16–45 — proof of life.** Answer every issue within 72h; ship one patch release
from user feedback; publish one build-story update ("what parents asked for").
Metrics: 150+ active installs, 3+ external contributors or reporters, first organic
sponsor, HACS analytics trend visible on vaskivskyi/ha-custom-analytics.

**Days 46–90 — widen the funnel.** Add beta channel; reply to SeTracker/Xplora demand
threads; one post in a MyKi parent group per genuine question; start a roadmap poll
(vote = sponsor perk, but anyone can read).
Metrics: 300+ active installs, 25+ stars/month sustained, 3–5 total sponsors (€10–40/mo),
first beta adopted by someone who isn't a friend.

## Honest expectations

- Comparable niche single-vendor integrations, after *years*: petkit ~2.2k active
  installs, petlibro ~1.4k (rank ~212 of all custom integrations); many quality ones
  sit under 200. MyKi Spot is one device from one vendor: 300–800 active installs in
  year one is a good outcome; 2k+ would require more devices or vendor attention.
- Sponsor conversion for OSS is brutally low: industry anecdotes run 0.1–0.5% of active
  users; a 2022 study found only ~40% of developers seeking sponsorship received *any*
  donation. At 500 installs expect **1–3 sponsors and €5–15/month**. The 90-day targets
  above are already the optimistic branch.
- What sponsorship realistically buys: coffee money and motivation, plus a signal of
  who to prioritize. It does not buy maintenance time — budget evenings accordingly,
  and say no to features that only one non-sponsor asks for.
- The compounding asset is HACS listing + SEO on "MyKi Home Assistant"; sponsor revenue
  follows installs with a long lag, not the other way around.
