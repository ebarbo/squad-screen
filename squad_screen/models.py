from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]
Role = Literal["start", "bench", "rotate", "rest"]
RunMode = Literal["live", "demo"]
Impact = Literal["negative", "slight_negative", "neutral", "slight_positive", "positive"]
InjuryRisk = Literal["baseline", "elevated", "high"]


class Player(BaseModel):
    id: str
    name: str
    position: str | None = None
    position_code: str | None = None
    nationality: str | None = None
    date_of_birth: str | None = None
    shirt_number: int | None = None
    source: str
    aliases: list[str] = Field(default_factory=list)


class Article(BaseModel):
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    snippet: str | None = None
    full_text: str | None = None
    paywalled: bool = False
    player_mentions: list[str] = Field(default_factory=list)
    fetch_status: str = "snippet_only"
    demo: bool = False


class SocialItem(BaseModel):
    platform: str
    author: str
    content: str
    timestamp: datetime | None = None
    url: str | None = None
    media_type: str = "post"
    player_id: str
    player_name: str
    fetch_status: str = "fetched"
    demo: bool = False


class Signal(BaseModel):
    player_id: str
    player_name: str
    category: str
    severity: Severity
    evidence: str
    source_url: str | None = None
    source_type: Literal["article", "social", "reported_social"]
    source_title: str | None = None
    demo: bool = False


class PerformanceAssessment(BaseModel):
    player_id: str
    player_name: str
    position: str | None = None
    position_code: str | None = None
    shirt_number: int | None = None
    estimated_impact: Impact
    injury_risk: InjuryRisk
    recommended_role: Role
    rationale: str
    signal_ids: list[int] = Field(default_factory=list)
    mention_count: int = 0


class LineupSlot(BaseModel):
    slot: str
    player: Player
    rationale: str
    recommended_role: Role


class LineupRecommendation(BaseModel):
    formation: str
    starting_xi: list[LineupSlot]
    bench: list[LineupSlot]
    rest: list[LineupSlot]
    rotation_notes: list[str] = Field(default_factory=list)
    summary: str


class CoverageGap(BaseModel):
    area: str
    reason: str
    impact: str


class TeamRef(BaseModel):
    id: str
    name: str
    short_name: str | None = None
    competition: str | None = None
    venue: str | None = None
    source: str
    crest_url: str | None = None


class Report(BaseModel):
    team: TeamRef
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    mode: RunMode
    lookback_days: int
    roster: list[Player]
    articles: list[Article]
    social_items: list[SocialItem]
    signals: list[Signal]
    assessments: list[PerformanceAssessment]
    lineup: LineupRecommendation
    coverage_gaps: list[CoverageGap]
    notes: list[str] = Field(default_factory=list)
    sources_attempted: list[str] = Field(default_factory=list)
