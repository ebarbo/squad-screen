from __future__ import annotations

import logging
from squad_screen.config import get_settings
from squad_screen.http import HttpClient
from squad_screen.models import CoverageGap, Player, TeamRef
from squad_screen.names import normalize_position, player_aliases
from squad_screen.roster.api_football import fetch_api_football
from squad_screen.roster.football_data import fetch_football_data
from squad_screen.roster.sportsdb import fetch_sportsdb
from squad_screen.roster.wikipedia import fetch_wikipedia
from squad_screen.teams import canonical_team_name

log = logging.getLogger(__name__)


def _roster_rank(players: list[Player]) -> tuple[int, int]:
    n = len(players)
    if 16 <= n <= 36:
        return (0, -n)
    if 11 <= n <= 45:
        return (1, -n)
    return (2, abs(n - 25))


class RosterResult:
    def __init__(
        self,
        team: TeamRef | None,
        players: list[Player],
        gaps: list[CoverageGap],
        attempted: list[str],
    ) -> None:
        self.team = team
        self.players = players
        self.gaps = gaps
        self.attempted = attempted


async def resolve_roster(client: HttpClient, team_query: str) -> RosterResult:
    settings = get_settings()
    query = canonical_team_name(team_query)
    attempted: list[str] = []
    gaps: list[CoverageGap] = []

    providers = [
        (
            "api-football",
            bool(settings.api_football_key),
            lambda: fetch_api_football(client, query, settings.api_football_key),
            "API_FOOTBALL_KEY not set",
        ),
        (
            "football-data.org",
            bool(settings.football_data_api_key),
            lambda: fetch_football_data(client, query, settings.football_data_api_key),
            "FOOTBALL_DATA_API_KEY not set",
        ),
        (
            "thesportsdb",
            True,
            lambda: fetch_sportsdb(client, query, settings.thesportsdb_api_key),
            "TheSportsDB unavailable",
        ),
        (
            "wikipedia",
            True,
            lambda: fetch_wikipedia(client, query),
            "Wikipedia squad table not found",
        ),
    ]

    best: RosterResult | None = None
    for name, available, factory, missing_reason in providers:
        attempted.append(name)
        if not available:
            gaps.append(
                CoverageGap(
                    area=f"roster:{name}",
                    reason=missing_reason,
                    impact="Squad may be resolved from a later fallback source.",
                )
            )
            continue
        try:
            team, players = await factory()
        except Exception as exc:  # noqa: BLE001 — collector isolation
            log.warning("Roster provider %s failed: %s", name, exc)
            gaps.append(
                CoverageGap(
                    area=f"roster:{name}",
                    reason=f"{name} raised {type(exc).__name__}: {exc}",
                    impact="Trying the next roster source.",
                )
            )
            continue
        if team and players:
            log.info("Roster from %s: %s (%s players)", name, team.name, len(players))
            for player in players:
                if not player.position_code:
                    player.position_code = normalize_position(player.position)
                if not player.aliases:
                    player.aliases = player_aliases(player.name)
            result = RosterResult(team, players, list(gaps), list(attempted))
            if best is None or _roster_rank(players) < _roster_rank(best.players):
                best = result
            if 16 <= len(players) <= 36:
                best.attempted = attempted
                best.gaps = gaps
                return best
        else:
            gaps.append(
                CoverageGap(
                    area=f"roster:{name}",
                    reason=f"{name} returned no squad for {query!r}",
                    impact="Trying the next roster source.",
                )
            )

    if best:
        best.attempted = attempted
        best.gaps = gaps
        return best

    fallback_team = TeamRef(
        id="unresolved",
        name=query,
        source="unresolved",
    )
    gaps.append(
        CoverageGap(
            area="roster",
            reason=f"Could not resolve a current squad for {query!r} from any provider.",
            impact="News and social screening cannot be player-specific.",
        )
    )
    return RosterResult(fallback_team, [], gaps, attempted)
