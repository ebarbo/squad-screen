# Squad Screen

Match-day readiness briefing for a football (soccer) first-team squad.

Give it a club name such as `Barcelona`. It looks up the current roster, gathers public news (and social posts only where an official API key exists) from the last three days, flags lifestyle and medical signals with **severity + an evidence quote**, and writes a recommended starting XI, bench, and rest list with a short rationale for each decision.

**It does not invent articles, social posts, injuries, or rumours.** If a source is missing, paywalled, or returns nothing, that section stays empty and the reason is listed under Coverage gaps.

Primary target: top-flight European clubs.

---

## Quick start (demo, offline, no API keys)

Python 3.11+

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m squad_screen demo Barcelona
```

That command does not use the network. It reads bundled fixtures and writes a full structured report:

- `reports/<timestamp>_fc_barcelona_demo.md`
- `reports/<timestamp>_fc_barcelona_demo.json`
- copies as `reports/latest.md` and `reports/latest.json`

**Committed samples**

- Demo shape (Barcelona, labelled fixture data): [`reports/sample_barcelona_demo.md`](reports/sample_barcelona_demo.md)
- First live screen (PSV Eindhoven): [`reports/sample_psv_eindhoven_live.md`](reports/sample_psv_eindhoven_live.md) · [`reports/sample_psv_eindhoven_live.json`](reports/sample_psv_eindhoven_live.json)

Every article and post in demo mode is labelled `demo`. Treat it as a shape example, not current news about those players.

---

## Demo vs live

| | `demo` | `screen` (live) |
| --- | --- | --- |
| Network | None | Yes |
| API keys | None | All optional |
| Roster / articles / posts | Bundled fixtures | Fetched now |
| Empty sources | Still a full sample report | Lists stay empty; gaps are recorded |
| Invented copy | Never claimed as live | Never — no articles or posts are fabricated |

```bash
# Offline sample (no API keys)
python -m squad_screen demo Barcelona

# Live (works without keys; coverage gaps are listed when sources are missing)
python -m squad_screen screen Barcelona
python -m squad_screen screen "PSV Eindhoven" --days 3
python -m squad_screen screen "Manchester City" --days 3 --verbose
```

### Local UI

```bash
python -m squad_screen serve --port 43123
```

Open http://127.0.0.1:43123. The form defaults to **Demo fixtures** so you can review a briefing with no keys. Switch the source to **Live collection** to hit real endpoints.

---

## What the report contains

1. **Roster** — players, positions, numbers, source of the squad
2. **Articles** — title, outlet, date, URL, fetch status (`fetched` / `snippet_only` / `paywalled` / `inaccessible`), player mentions
3. **Social items** — grouped by platform (Instagram and X first); first-party only with a key (and, for Instagram, an explicit username map), otherwise second-hand mentions copied from news (labelled `second_hand`)
4. **Signals** — category, severity (`low` / `medium` / `high`), evidence quote, source URL
5. **Per-player correlation** — estimated performance impact, injury-risk elevation, recommended role (`start` / `bench` / `rotate` / `rest`)
6. **Match-day organisation** — 4-3-3 starting XI, bench, rest/unavailable, rotation notes
7. **Coverage gaps** — which sources were skipped or empty, and why

Uncovered players are treated as **neutral**, not as confirmed-fit or confirmed-compromised.

---

## Live data: optional API keys

No environment variable is required. Live mode still:

1. Resolves a roster (TheSportsDB soccer search, then Wikipedia current-squad tables).
2. Queries Google News RSS and major football RSS feeds (BBC, Guardian, ESPN, Sky).
3. Tries to download open article text; marks paywalled or inaccessible URLs instead of guessing the body.

Copy the example file and fill in only what you have:

```bash
cp .env.example .env
```

| Variable | Where to get it | What it adds |
| --- | --- | --- |
| `THESPORTSDB_API_KEY` | [thesportsdb.com](https://www.thesportsdb.com) — default `123` is the free test key | Richer squad lookup |
| `FOOTBALL_DATA_API_KEY` | [football-data.org](https://www.football-data.org/client/register) | Alternative official squad |
| `API_FOOTBALL_KEY` | [api-football.com](https://www.api-football.com) | Alternative official squad |
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Extra article search |
| `GUARDIAN_API_KEY` | [open-platform.theguardian.com](https://open-platform.theguardian.com) | Guardian articles, often with body text |
| `GNEWS_API_KEY` | [gnews.io](https://gnews.io) | Extra article search |
| `TWITTER_BEARER_TOKEN` | [developer.x.com](https://developer.x.com) | First-party X/Twitter recent search |
| `INSTAGRAM_ACCESS_TOKEN` | [Meta for Developers](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-discovery) — long-lived User token | First-party Instagram via Business Discovery |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | IG user id of the observer professional account | Required together with the token |
| `INSTAGRAM_ENABLED` | default `true` | Set `false` to skip Instagram even when credentials are present |
| `INSTAGRAM_GRAPH_VERSION` | default `v21.0` | Graph API version (`v21.0` or later; Meta samples currently use later versions such as v26.0) |
| `INSTAGRAM_MAX_PLAYERS` | default `20` | Cap on mapped players queried per run |
| `INSTAGRAM_MAX_MEDIA` | default `10` | `media.limit(N)` per username |
| `INSTAGRAM_HANDLES_FILE` | default `config/instagram_handles.json` | Explicit player → Instagram username map |
| `OPENAI_API_KEY` | OpenAI | Optional classifier on **already collected** text only. Quotes that are not substrings of the source are discarded. |
| `OPENAI_MODEL` | default `gpt-4o-mini` | Model used if the OpenAI key is set |

**Social platforms without a supported public API** (TikTok, Facebook, and X if `TWITTER_BEARER_TOKEN` is unset) are listed as coverage gaps. Instagram is collected only through official Meta Business Discovery when credentials **and** a handle map are present. The tool does not scrape those sites.

HTTP tuning (also in `.env.example`): `HTTP_USER_AGENT`, `HTTP_TIMEOUT_SECONDS`, `NEWS_CONCURRENCY`.

---

## Instagram (Business Discovery)

Social collection **v1.1** can read recent public media from other Instagram **Business/Creator (professional)** accounts using the [Instagram API with Facebook Login — Business Discovery](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-discovery). This is the official Graph API path. HTML scraping, unofficial APIs, and cookie-session hacks are out of scope and are not implemented.

Default Graph version is **`v21.0`** (`INSTAGRAM_GRAPH_VERSION`). Override if your app is pinned to a later version.

### What it can and cannot do

| | |
| --- | --- |
| Can | Read public media metadata (caption, permalink, timestamp, media type) for **other professional** accounts, by **username** |
| Cannot | Search players by name; read **personal** Instagram accounts; invent captions or handles; fetch stories |

If a handle is missing, the account is personal, Graph returns an error, or media is empty in the lookback window (`--days`), that player is omitted from Instagram items and a **coverage gap** is recorded. Nothing is fabricated.

### Meta setup (high level)

1. Create a Meta app and add **Instagram API with Facebook Login** (not scraping, not Basic Display for other users).
2. Connect a Facebook Page to an Instagram **professional** account — this is the observer account whose IG user id you put in `INSTAGRAM_BUSINESS_ACCOUNT_ID`.
3. Generate a **long-lived User access token** with at least `instagram_basic`, `instagram_manage_insights`, and `pages_read_engagement`. Apps in Development can only see users/roles on the app; **Advanced Access** (App Review) is required to query arbitrary professional accounts in production.
4. Copy `.env.example` to `.env` and set `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_BUSINESS_ACCOUNT_ID`. Do not commit `.env`.
5. Copy [`config/instagram_handles.example.json`](config/instagram_handles.example.json) to `config/instagram_handles.json` and map roster **display names or ids** to usernames **without `@`**. Live mode never guesses handles.

Example Graph call (token not shown):

```
GET https://graph.facebook.com/v21.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}
  ?fields=business_discovery.username({username}){username,website,followers_count,media.limit(N){id,caption,media_type,permalink,timestamp,like_count,comments_count}}
```

Collection runs automatically in `squad-screen screen` when both credentials are set (and `INSTAGRAM_ENABLED` is not `false`). X/Twitter is unchanged if Instagram env vars are unset. Demo mode (`python -m squad_screen demo Barcelona`) still uses labelled fixture posts and does not call Meta.

Handle map formats:

```json
{
  "Lamine Yamal": "demo_lamineyamal",
  "10": "demo_lamineyamal"
}
```

```json
{
  "players": [
    {"id": "10", "name": "Lamine Yamal", "username": "demo_lamineyamal"}
  ]
}
```

CSV (`id,name,username`) is also accepted. The Barcelona demo map (fake handles only) lives at [`squad_screen/fixtures/instagram_handles.json`](squad_screen/fixtures/instagram_handles.json).

---

## Integrity (live path)

- Live collection only records what sources actually return.
- If news or social APIs are missing or empty, those lists are empty. The report still includes roster (when resolved), assessments, a lineup from available evidence, and Coverage gaps.
- Paywalled pages are `paywalled` with snippet-only text when that is all that was available.
- The optional LLM cannot add a signal unless the evidence quote appears in collected text.
- Tests in `tests/test_live_empty.py` assert that mocked empty sources do not produce invented articles, posts, or signals.

---

## Project layout

```
squad_screen/
  roster/      TheSportsDB, football-data.org, API-Football, Wikipedia
  news/        Google News RSS, site RSS, NewsAPI, Guardian, GNews + article extract
  social/      X API if keyed; Instagram Business Discovery if token + handle map; second-hand mentions from news
  analyzer/    keyword/rules heuristics; optional OpenAI regrade
  report/      4-3-3 selector + Markdown/JSON writer
  web/         FastAPI briefing UI
  fixtures/    offline demo bundle (Barcelona)
tests/
reports/sample_barcelona_demo.md
reports/sample_psv_eindhoven_live.md
.env.example
pyproject.toml
requirements.txt
```

```bash
pytest
```

---

## Troubleshooting

- **Demo looks “too complete”** — that is expected. It is fixture data. Look for `DEMO DATA` at the top of the Markdown file.
- **Live roster is short or odd** — Wikipedia and TheSportsDB can lag or disagree. Set `FOOTBALL_DATA_API_KEY` or `API_FOOTBALL_KEY` for another source.
- **Live articles list is empty** — RSS may be blocked, filtered, or truly quiet for that window. That is a valid result, not a crash.
- **Social is empty** — expected without `TWITTER_BEARER_TOKEN` and without Instagram credentials + handle map. TikTok/Facebook are never first-party. Missing Instagram handles are coverage gaps, not guessed usernames.
- **`python -m squad_screen` not found** — activate the venv and `pip install -e .`.
