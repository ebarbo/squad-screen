from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

from squad_screen.analyzer.correlate import correlate
from squad_screen.analyzer.llm import llm_enrich
from squad_screen.analyzer.rules import analyze_sources
from squad_screen.config import get_settings
from squad_screen.demo import demo_articles, demo_roster, demo_social, demo_team, load_demo_bundle
from squad_screen.http import HttpClient
from squad_screen.models import CoverageGap, Report, RunMode
from squad_screen.news import collect_news
from squad_screen.report.lineup import recommend_lineup
from squad_screen.report.writer import write_report
from squad_screen.roster import resolve_roster
from squad_screen.social import collect_social

log = logging.getLogger(__name__)

Progress = Callable[[str], Awaitable[None] | None]


async def _emit(progress: Progress | None, message: str) -> None:
    log.info(message)
    if progress is None:
        return
    result = progress(message)
    if hasattr(result, "__await__"):
        await result  # type: ignore[misc]


async def run_screen(
    team_query: str,
    *,
    mode: RunMode = "live",
    lookback_days: int | None = None,
    report_dir: Path | None = None,
    progress: Progress | None = None,
) -> tuple[Report, Path, Path]:
    settings = get_settings()
    days = lookback_days or settings.lookback_days
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    out_dir = Path(report_dir or settings.report_dir)

    if mode == "demo":
        report = await _run_demo(team_query, now, start, days)
        md_path, json_path = write_report(report, out_dir)
        await _emit(progress, f"Wrote {md_path}")
        return report, md_path, json_path

    client = HttpClient()
    try:
        report = await _run_live(client, team_query, now, start, days, progress)
    finally:
        await client.aclose()
    md_path, json_path = write_report(report, out_dir)
    await _emit(progress, f"Wrote {md_path}")
    return report, md_path, json_path


async def _run_demo(team_query: str, now: datetime, start: datetime, days: int) -> Report:
    bundle = load_demo_bundle(team_query)
    team = demo_team(bundle)
    roster = demo_roster(bundle)
    articles = demo_articles(bundle, now)
    social = demo_social(bundle, now)
    signals = analyze_sources(roster, articles, social)
    mentions = Counter(name for article in articles for name in article.player_mentions)
    assessments = correlate(roster, signals, mentions)
    lineup = recommend_lineup(roster, assessments)
    gaps = [
        CoverageGap(
            area="demo",
            reason="This report is built from bundled fixtures, not live HTTP sources.",
            impact="Use `squad-screen screen <team>` for a real collection. Demo content is labelled throughout.",
        ),
        CoverageGap(
            area="social:Instagram",
            reason="Demo includes labelled sample Instagram items; live mode cannot fetch Instagram without tokens.",
            impact="Treat demo social items as illustrative only.",
        ),
    ]
    return Report(
        team=team,
        generated_at=now,
        window_start=start,
        window_end=now,
        mode="demo",
        lookback_days=days,
        roster=roster,
        articles=articles,
        social_items=social,
        signals=signals,
        assessments=assessments,
        lineup=lineup,
        coverage_gaps=gaps,
        notes=[
            "DEMO MODE. Articles, posts, and signals are fixture data shaped like a real report.",
            "They must not be treated as current news about the named players.",
        ],
        sources_attempted=["demo_fixture"],
    )


async def _run_live(
    client: HttpClient,
    team_query: str,
    now: datetime,
    start: datetime,
    days: int,
    progress: Progress | None,
) -> Report:
    attempted: list[str] = []
    gaps: list[CoverageGap] = []
    notes: list[str] = [
        "Live mode only records sources that responded. Empty sections mean nothing was found, not that nothing happened.",
        "Paywalled or inaccessible articles are listed with status; their body text is not invented.",
    ]

    await _emit(progress, f"Resolving roster for {team_query!r}")
    roster_result = await resolve_roster(client, team_query)
    attempted.extend(f"roster:{s}" for s in roster_result.attempted)
    gaps.extend(roster_result.gaps)
    team = roster_result.team
    roster = roster_result.players
    assert team is not None

    articles = []
    social = []
    if roster:
        await _emit(progress, f"Collecting news for {len(roster)} players (last {days} days)")
        articles, news_gaps, news_attempted = await collect_news(
            client, team.name, roster, start, now
        )
        gaps.extend(news_gaps)
        attempted.extend(f"news:{s}" for s in news_attempted)
        await _emit(progress, f"News items retained: {len(articles)}")

        await _emit(progress, "Collecting social (public APIs + second-hand mentions)")
        social, social_gaps, social_attempted = await collect_social(
            client, roster, articles, start
        )
        gaps.extend(social_gaps)
        attempted.extend(f"social:{s}" for s in social_attempted)
        await _emit(progress, f"Social items retained: {len(social)}")
    else:
        gaps.append(
            CoverageGap(
                area="pipeline",
                reason="No roster — skipping player-specific news and social collection.",
                impact="Report will not contain articles, posts, or signals.",
            )
        )

    await _emit(progress, "Analyzing collected text (rules; LLM only if key present)")
    signals = analyze_sources(roster, articles, social)
    settings = get_settings()
    if settings.openai_api_key and roster:
        chunks = []
        for player in roster:
            for article in articles:
                if player.name not in article.player_mentions:
                    continue
                text = "\n".join(filter(None, [article.title, article.snippet, article.full_text]))
                if text:
                    chunks.append(
                        (player.id, player.name, text, article.url, "article", False)
                    )
            for item in social:
                if item.player_id == player.id and item.content:
                    chunks.append(
                        (
                            player.id,
                            player.name,
                            item.content,
                            item.url,
                            "social" if item.fetch_status != "second_hand" else "reported_social",
                            False,
                        )
                    )
        llm_signals = await llm_enrich(client, chunks[:30])
        if llm_signals:
            signals.extend(llm_signals)
            notes.append(
                f"LLM classifier added {len(llm_signals)} evidence-checked signal(s); quotes not present in source text were discarded."
            )
        else:
            notes.append("OPENAI_API_KEY present but no additional evidence-checked signals were added.")
    else:
        gaps.append(
            CoverageGap(
                area="analyzer:llm",
                reason="OPENAI_API_KEY not set; using deterministic keyword/rules analyzer only.",
                impact="Severity still assigned from evidence quotes; nuance may be lower.",
            )
        )

    mentions: Counter[str] = Counter()
    for article in articles:
        mentions.update(article.player_mentions)
    assessments = correlate(roster, signals, mentions)
    lineup = recommend_lineup(roster, assessments)

    if not articles and not social and roster:
        notes.append(
            "Collection finished with no articles and no social items. Signals are empty on purpose."
        )

    return Report(
        team=team,
        generated_at=now,
        window_start=start,
        window_end=now,
        mode="live",
        lookback_days=days,
        roster=roster,
        articles=articles,
        social_items=social,
        signals=signals,
        assessments=assessments,
        lineup=lineup,
        coverage_gaps=gaps,
        notes=notes,
        sources_attempted=attempted,
    )
