from __future__ import annotations

from squad_screen.models import (
    LineupRecommendation,
    LineupSlot,
    PerformanceAssessment,
    Player,
)
from squad_screen.names import group_for, normalize_position

FORMATION = "4-3-3"
SLOTS = [
    ("GK", "GK"),
    ("RB", "DEF"),
    ("RCB", "DEF"),
    ("LCB", "DEF"),
    ("LB", "DEF"),
    ("RCM", "MID"),
    ("CM", "MID"),
    ("LCM", "MID"),
    ("RW", "FWD"),
    ("ST", "FWD"),
    ("LW", "FWD"),
]

ROLE_RANK = {"start": 0, "rotate": 1, "bench": 2, "rest": 3}
IMPACT_RANK = {
    "positive": 0,
    "slight_positive": 1,
    "neutral": 2,
    "slight_negative": 3,
    "negative": 4,
}

PREFERRED_SLOT = {
    "GK": ["GK"],
    "RB": ["RB", "WB", "CB"],
    "LB": ["LB", "WB", "CB"],
    "RCB": ["CB", "RB"],
    "LCB": ["CB", "LB"],
    "RCM": ["CM", "DM", "AM"],
    "CM": ["DM", "CM", "AM"],
    "LCM": ["AM", "CM", "DM"],
    "RW": ["RW", "ST", "AM"],
    "ST": ["ST", "RW", "LW"],
    "LW": ["LW", "ST", "AM"],
}


def _score(
    player: Player,
    assessment: PerformanceAssessment,
    codes: list[str] | None = None,
) -> tuple:
    code = assessment.position_code or normalize_position(player.position)
    if codes:
        if code == codes[0]:
            fit = 0
        elif code in codes:
            fit = 1
        else:
            fit = 2
    else:
        fit = 0
    shirt = player.shirt_number
    likely_regular = assessment.mention_count > 0 or (shirt is not None and shirt <= 11)
    striker_pref = 0
    if codes and codes[0] == "ST":
        pos = (player.position or "").lower()
        striker_pref = 0 if "strik" in pos or "centre-forward" in pos or "center-forward" in pos else 1
    return (
        fit,
        0 if likely_regular else 1,
        ROLE_RANK.get(assessment.recommended_role, 9),
        IMPACT_RANK.get(assessment.estimated_impact, 9),
        0 if assessment.injury_risk == "baseline" else 1 if assessment.injury_risk == "elevated" else 2,
        striker_pref,
        -assessment.mention_count,
        shirt if shirt is not None else 99,
        player.name,
    )


def recommend_lineup(
    players: list[Player],
    assessments: list[PerformanceAssessment],
) -> LineupRecommendation:
    by_id = {p.id: p for p in players}
    assess_by_id = {a.player_id: a for a in assessments}
    remaining = list(players)

    def take_for_slot(slot: str, codes: list[str]) -> Player | None:
        def eligible(player: Player) -> bool:
            assessment = assess_by_id.get(player.id)
            if assessment and assessment.recommended_role == "rest":
                return False
            code = (assessment.position_code if assessment else None) or normalize_position(
                player.position
            )
            group = group_for(code)
            wanted_group = "GK" if slot == "GK" else (
                "DEF" if slot in {"RB", "RCB", "LCB", "LB"} else
                "MID" if slot in {"RCM", "CM", "LCM"} else "FWD"
            )
            if code in codes:
                return True
            # fallback to group match if we run dry
            return False if any(
                ((assess_by_id.get(p.id).position_code if assess_by_id.get(p.id) else None)
                 or normalize_position(p.position)) in codes
                for p in remaining
            ) else group == wanted_group

        pool = [p for p in remaining if eligible(p)]
        if not pool:
            pool = [
                p for p in remaining
                if (assess_by_id.get(p.id) and assess_by_id[p.id].recommended_role != "rest")
            ]
        if not pool:
            return None
        pool.sort(key=lambda p: _score(p, assess_by_id[p.id], codes))
        chosen = pool[0]
        remaining.remove(chosen)
        return chosen

    starting: list[LineupSlot] = []
    for slot, _group in SLOTS:
        codes = PREFERRED_SLOT[slot]
        player = take_for_slot(slot, codes)
        if not player:
            continue
        assessment = assess_by_id[player.id]
        starting.append(
            LineupSlot(
                slot=slot,
                player=player,
                rationale=_slot_rationale(slot, assessment),
                recommended_role=assessment.recommended_role
                if assessment.recommended_role in {"start", "rotate", "bench"}
                else "start",
            )
        )

    rest_slots: list[LineupSlot] = []
    bench: list[LineupSlot] = []
    # leftover
    leftovers = sorted(remaining, key=lambda p: _score(p, assess_by_id[p.id]))
    for player in leftovers:
        assessment = assess_by_id[player.id]
        slot_name = (assessment.position_code or group_for(assessment.position_code) or "SQ")
        entry = LineupSlot(
            slot=slot_name,
            player=player,
            rationale=assessment.rationale,
            recommended_role=assessment.recommended_role,
        )
        if assessment.recommended_role == "rest":
            rest_slots.append(entry)
        else:
            bench.append(entry)

    bench = bench[:9]
    notes: list[str] = []
    rotated = [a for a in assessments if a.recommended_role == "rotate"]
    rested = [a for a in assessments if a.recommended_role == "rest"]
    if rotated:
        notes.append(
            "Minutes management: "
            + ", ".join(a.player_name for a in rotated[:6])
            + ("." if len(rotated) <= 6 else f" (+{len(rotated)-6} more).")
        )
    if rested:
        notes.append(
            "Unavailable / rest: " + ", ".join(a.player_name for a in rested) + "."
        )
    flagged_starters = [
        s for s in starting if assess_by_id[s.player.id].recommended_role in {"rotate", "bench"}
    ]
    if flagged_starters:
        notes.append(
            "Started despite a caution flag: "
            + ", ".join(s.player.name for s in flagged_starters)
            + " — no cleaner like-for-like option ranked higher."
        )

    xi_names = ", ".join(f"{s.slot} {s.player.name}" for s in starting)
    summary = (
        f"Recommended {FORMATION} ({len(starting)} named): {xi_names}. "
        "Roles follow collected signals only; uncovered players are treated as neutral, not presumed fit."
    )
    return LineupRecommendation(
        formation=FORMATION,
        starting_xi=starting,
        bench=bench,
        rest=rest_slots,
        rotation_notes=notes,
        summary=summary,
    )


def _slot_rationale(slot: str, assessment: PerformanceAssessment) -> str:
    prefix = f"{slot} — {assessment.recommended_role}. "
    return prefix + assessment.rationale
