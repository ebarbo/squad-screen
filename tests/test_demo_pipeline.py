from __future__ import annotations

import asyncio
from pathlib import Path

from squad_screen.models import Article, Player, SocialItem
from squad_screen.pipeline import run_screen
from squad_screen.report.writer import render_markdown


def test_demo_barcelona_offline(tmp_path: Path):
    report, md_path, json_path = asyncio.run(
        run_screen("Barcelona", mode="demo", lookback_days=3, report_dir=tmp_path)
    )
    assert report.mode == "demo"
    assert len(report.roster) >= 18
    assert report.articles, "demo must include articles"
    assert report.social_items, "demo must include social items"
    assert report.signals, "demo must extract signals from fixtures"
    assert len(report.lineup.starting_xi) == 11
    assert report.lineup.bench
    assert any(s.player_name == "Dani Olmo" and s.recommended_role == "rest" for s in report.assessments)
    assert any(g.area == "demo" for g in report.coverage_gaps)
    assert all(a.demo for a in report.articles)
    md = md_path.read_text(encoding="utf-8")
    assert "DEMO" in md
    assert "Coverage gaps" in md
    assert json_path.exists()
    # Never claim live collection in demo
    assert report.mode != "live"


def test_demo_markdown_shape(tmp_path: Path):
    report, _, _ = asyncio.run(
        run_screen("Barcelona", mode="demo", report_dir=tmp_path)
    )
    md = render_markdown(report)
    assert "Starting XI" in md
    assert "Araújo" in md or "Araujo" in md
    assert any("paywalled" in a.fetch_status or a.paywalled for a in report.articles)
