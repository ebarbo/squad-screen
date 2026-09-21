from __future__ import annotations

import asyncio
from pathlib import Path

from squad_screen.models import CoverageGap, Player, TeamRef
from squad_screen.pipeline import run_screen
from squad_screen.roster import RosterResult


async def _roster(_client, query: str) -> RosterResult:
    team = TeamRef(id="mock", name="FC Barcelona", source="mock")
    players = [
        Player(
            id="8",
            name="Pedri",
            position="Midfielder",
            position_code="CM",
            source="mock",
            aliases=["Pedri"],
        )
    ]
    return RosterResult(team, players, [], ["mock"])


async def _news(*_args, **_kwargs):
    return (
        [],
        [CoverageGap(area="news", reason="No in-window articles mentioning the team or its players were found.", impact="empty")],
        ["google-news-rss"],
    )


async def _social(*_args, **_kwargs):
    return (
        [],
        [CoverageGap(area="social", reason="No first-party or second-hand social items were collected in the window.", impact="empty")],
        ["x-twitter-recent-search", "instagram-business-discovery"],
    )


def test_live_empty_sources_do_not_invent(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("squad_screen.pipeline.resolve_roster", _roster)
    monkeypatch.setattr("squad_screen.pipeline.collect_news", _news)
    monkeypatch.setattr("squad_screen.pipeline.collect_social", _social)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    report, md_path, _ = asyncio.run(
        run_screen("Barcelona", mode="live", lookback_days=3, report_dir=tmp_path)
    )
    assert report.mode == "live"
    assert report.articles == []
    assert report.social_items == []
    assert report.signals == []
    assert any("No in-window articles" in g.reason for g in report.coverage_gaps)
    md = md_path.read_text(encoding="utf-8")
    assert "No articles collected" in md or "No articles collected in this window" in md
    assert "Pedri" in md
    # Neutral / start is OK when there is no evidence; fabricating news is not.
    pedri = next(a for a in report.assessments if a.player_name == "Pedri")
    assert "No lifestyle or medical flags" in pedri.rationale
