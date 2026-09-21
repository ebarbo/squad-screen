from __future__ import annotations

from collections import defaultdict

from squad_screen.analyzer.rules import SEVERITY_RANK
from squad_screen.models import (
    PerformanceAssessment,
    Player,
    Signal,
)
from squad_screen.names import normalize_position

NEGATIVE = {
    "injury",
    "late_night_partying",
    "alcohol",
    "fatigue",
    "off_field_incident",
    "emotional_state",
    "conflict",
    "nutrition",
    "travel",
}
POSITIVE = {"rest", "readiness"}


def correlate(
    players: list[Player],
    signals: list[Signal],
    mention_counts: dict[str, int],
) -> list[PerformanceAssessment]:
    by_player: dict[str, list[Signal]] = defaultdict(list)
    for signal in signals:
        by_player[signal.player_id].append(signal)

    assessments: list[PerformanceAssessment] = []
    for player in players:
        related = by_player.get(player.id, [])
        role, impact, risk, rationale = _decide(player, related)
        assessments.append(
            PerformanceAssessment(
                player_id=player.id,
                player_name=player.name,
                position=player.position,
                position_code=player.position_code or normalize_position(player.position),
                shirt_number=player.shirt_number,
                estimated_impact=impact,
                injury_risk=risk,
                recommended_role=role,
                rationale=rationale,
                signal_ids=[],
                mention_count=mention_counts.get(player.name, 0),
            )
        )
    return assessments


def _decide(player: Player, signals: list[Signal]) -> tuple[str, str, str, str]:
    neg = [s for s in signals if s.category in NEGATIVE]
    pos = [s for s in signals if s.category in POSITIVE]
    high_neg = [s for s in neg if s.severity == "high"]
    med_neg = [s for s in neg if s.severity == "medium"]
    injuries = [s for s in signals if s.category == "injury"]
    high_injury = any(s.severity == "high" for s in injuries)
    med_injury = any(s.severity == "medium" for s in injuries)
    incidents = [s for s in signals if s.category == "off_field_incident" and s.severity == "high"]
    lifestyle_high = [
        s for s in signals
        if s.category in {"late_night_partying", "alcohol"} and s.severity in {"high", "medium"}
    ]

    risk = "baseline"
    if high_injury:
        risk = "high"
    elif med_injury or lifestyle_high:
        risk = "elevated"

    if high_injury or incidents:
        role = "rest"
        impact = "negative"
    elif len(high_neg) >= 1 or len(med_neg) >= 2:
        role = "bench"
        impact = "negative" if high_neg else "slight_negative"
    elif med_neg or (lifestyle_high and not pos):
        role = "rotate"
        impact = "slight_negative"
    elif pos and not neg:
        role = "start"
        impact = "slight_positive" if any(s.severity != "low" for s in pos) else "positive"
        # low positive readiness still start
        impact = "slight_positive"
    elif not signals:
        role = "start"
        impact = "neutral"
    else:
        role = "start"
        impact = "slight_negative" if neg else "neutral"

    # Younger/less mentioned players with no signals stay eligible but ranking happens later
    bits: list[str] = []
    if not signals:
        bits.append("No lifestyle or medical flags in the collected window.")
    else:
        for signal in sorted(signals, key=lambda s: -SEVERITY_RANK[s.severity])[:4]:
            bits.append(f"{signal.category} ({signal.severity}): “{signal.evidence[:140]}”")
    if role == "rest":
        bits.append("Recommended out of the matchday squad until cleared.")
    elif role == "bench":
        bits.append("Start only if no like-for-like alternative is available.")
    elif role == "rotate":
        bits.append("Usable, but minutes should be managed.")
    return role, impact, risk, " ".join(bits)
