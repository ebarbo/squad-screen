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
3. **Social items** — platform, timestamp, link, content; first-party only with a key, otherwise second-hand mentions copied from news (labelled `second_hand`)
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
| `OPENAI_API_KEY` | OpenAI | Optional classifier on **already collected** text only. Quotes that are not substrings of the source are discarded. |
| `OPENAI_MODEL` | default `gpt-4o-mini` | Model used if the OpenAI key is set |

**Social platforms without a supported public API** (Instagram, TikTok, Facebook, and X if `TWITTER_BEARER_TOKEN` is unset) are listed as coverage gaps. The tool does not scrape those sites.

HTTP tuning (also in `.env.example`): `HTTP_USER_AGENT`, `HTTP_TIMEOUT_SECONDS`, `NEWS_CONCURRENCY`.

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
  social/      X API if keyed; second-hand mentions extracted from news
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
- **Social is empty** — expected without `TWITTER_BEARER_TOKEN`. Instagram/TikTok/Facebook are never first-party in v1.
- **`python -m squad_screen` not found** — activate the venv and `pip install -e .`.
