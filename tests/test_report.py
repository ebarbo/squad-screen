from __future__ import annotations

from squad_screen.analyzer.correlate import correlate
from squad_screen.models import Player, Signal
from squad_screen.report.lineup import recommend_lineup
from squad_screen.report.writer import render_markdown
from squad_screen.models import (
    CoverageGap,
    LineupRecommendation,
    LineupSlot,
    PerformanceAssessment,
    Report,
    TeamRef,
)
from datetime import datetime, timezone


def _player(pid: str, name: str, code: str, shirt: int) -> Player:
    return Player(
        id=pid,
        name=name,
        position=code,
        position_code=code,
        shirt_number=shirt,
        source="test",
        aliases=[name],
    )


def _squad() -> list[Player]:
    return [
        _player("gk1", "Keeper One", "GK", 1),
        _player("gk2", "Keeper Two", "GK", 13),
        _player("rb", "Right Back", "RB", 2),
        _player("rcb", "Right Centre", "CB", 4),
        _player("lcb", "Left Centre", "CB", 5),
        _player("lb", "Left Back", "LB", 3),
        _player("cb3", "Spare Centre", "CB", 15),
        _player("cm1", "Mid One", "CM", 8),
        _player("cm2", "Mid Two", "CM", 6),
        _player("cm3", "Mid Three", "DM", 21),
        _player("cm4", "Mid Four", "AM", 16),
        _player("rw", "Right Wing", "RW", 10),
        _player("st", "Striker", "ST", 9),
        _player("lw", "Left Wing", "LW", 11),
        _player("st2", "Striker Two", "ST", 7),
        _player("inj", "Injured Star", "AM", 20),
    ]


def test_high_injury_maps_to_rest():
    players = _squad()
    injured = next(p for p in players if p.id == "inj")
    signals = [
        Signal(
            player_id=injured.id,
            player_name=injured.name,
            category="injury",
            severity="high",
            evidence="ruled out after a muscle injury",
            source_type="article",
        )
    ]
    assessments = correlate(players, signals, {})
    by_id = {a.player_id: a for a in assessments}
    assert by_id["inj"].recommended_role == "rest"
    assert by_id["inj"].injury_risk == "high"
    assert by_id["inj"].estimated_impact == "negative"
    assert by_id["gk1"].recommended_role == "start"


def test_lineup_has_eleven_and_keeps_injured_out():
    players = _squad()
    signals = [
        Signal(
            player_id="inj",
            player_name="Injured Star",
            category="injury",
            severity="high",
            evidence="ruled out",
            source_type="article",
        )
    ]
    assessments = correlate(players, signals, {"Right Wing": 4, "Striker": 3})
    lineup = recommend_lineup(players, assessments)
    assert len(lineup.starting_xi) == 11
    starter_ids = {s.player.id for s in lineup.starting_xi}
    assert "inj" not in starter_ids
    assert any(s.player.id == "inj" for s in lineup.rest)
    slots = [s.slot for s in lineup.starting_xi]
    assert slots.count("GK") == 1
    assert lineup.formation == "4-3-3"


def test_markdown_contains_required_sections():
    now = datetime.now(timezone.utc)
    players = _squad()[:11]
    assessments = correlate(players, [], {})
    lineup = recommend_lineup(players, assessments)
    report = Report(
        team=TeamRef(id="t", name="Test FC", source="test"),
        generated_at=now,
        window_start=now,
        window_end=now,
        mode="demo",
        lookback_days=3,
        roster=players,
        articles=[],
        social_items=[],
        signals=[],
        assessments=assessments,
        lineup=lineup,
        coverage_gaps=[
            CoverageGap(area="news", reason="none found", impact="empty articles")
        ],
        notes=["empty on purpose"],
        sources_attempted=["test"],
    )
    md = render_markdown(report)
    for heading in (
        "# Squad Screen",
        "## Match-day recommendation",
        "### Starting XI",
        "### Bench",
        "## Signals",
        "## Articles",
        "## Social items",
        "## Roster",
        "## Coverage gaps",
    ):
        assert heading in md
    assert "Test FC" in md
