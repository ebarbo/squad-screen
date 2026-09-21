from __future__ import annotations

import re
from dataclasses import dataclass

from squad_screen.models import Article, Player, Signal, SocialItem, Severity
from squad_screen.names import fold

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Rule:
    category: str
    severity: Severity
    pattern: re.Pattern[str]
    polarity: str = "negative"  # negative | positive


RULES: list[Rule] = [
    Rule("injury", "high", re.compile(
        r"\b(acl|achilles|fracture[ds]?|broken|rupture[ds]?|surgery|operation|"
        r"ruled out|out for (the )?(season|weeks|months)|indefinitely|"
        r"stretchered|hospitalised|hospitalized)\b", re.I
    )),
    Rule("injury", "medium", re.compile(
        r"\b(hamstring|groin|calf|knock|tightness|scan|mri|physio|injury doubt|"
        r"failed (a |the )?fitness test|twinge|muscle (issue|problem|injury)|ankle sprain|"
        r"not fit|not fully fit|sidelined|picked up a|"
        r"injur(?:y|ed|ies)|injury (scare|setback|list))\b", re.I
    )),
    Rule("injury", "low", re.compile(
        r"\b(minor knock|precaution|checked over|nursing a)\b", re.I
    )),
    Rule("late_night_partying", "high", re.compile(
        r"\b(4\s*a\.?m\.?|5\s*a\.?m\.?|all-nighter|left the club at|"
        r"stumbled out|drunk(en)? (night|exit)|nightclub until)\b", re.I
    )),
    Rule("late_night_partying", "medium", re.compile(
        r"\b(nightclub|night club|disco(theque)?|party(ing)? until|"
        r"seen leaving (a |the )?(club|bar)|nightlife|vip (area|table)|"
        r"after-party|afterparty)\b", re.I
    )),
    Rule("late_night_partying", "low", re.compile(
        r"\b(evening event|fashion (show|event|party)|awards? (night|after)|"
        r"gala|launch party)\b", re.I
    )),
    Rule("alcohol", "high", re.compile(
        r"\b(drunk|intoxicated|hungover|binge|alcohol (issue|problem)|"
        r"breathaly[sz]er)\b", re.I
    )),
    Rule("alcohol", "medium", re.compile(
        r"\b(drinking|shots|champagne|vodka|beer pong|on the beers)\b", re.I
    )),
    Rule("alcohol", "low", re.compile(
        r"\b(toast|glass of (wine|champagne)|celebratory drink)\b", re.I
    )),
    Rule("fatigue", "high", re.compile(
        r"\b(exhausted|burnt out|burned out|no energy|could not finish|"
        r"laboured|labored)\b", re.I
    )),
    Rule("fatigue", "medium", re.compile(
        r"\b(fatigue|tired|jet[- ]lag|heavy legs|"
        r"workload|lack of rest|needs rest)\b", re.I
    )),
    Rule("off_field_incident", "high", re.compile(
        r"\b(arrested|charged|police|assault|fight|crash|scandal|"
        r"investigation|restraining order|court)\b", re.I
    )),
    Rule("off_field_incident", "medium", re.compile(
        r"\b(incident|altercation|confronted|security|ejected|"
        r"banned from)\b", re.I
    )),
    Rule("emotional_state", "medium", re.compile(
        r"\b(heartbroken|furious|angry outburst|mental health|"
        r"depression|in tears|visibly upset|feud)\b", re.I
    )),
    Rule("emotional_state", "low", re.compile(
        r"\b(frustrated|unhappy|annoyed|downbeat)\b", re.I
    )),
    Rule("travel", "medium", re.compile(
        r"\b(long-haul|red[- ]eye|overnight flight|jetted|flew back late|"
        r"delayed flight)\b", re.I
    )),
    Rule("travel", "low", re.compile(
        r"\b(airport|holiday|vacation|flew|travelled|traveled|trip to)\b", re.I
    )),
    Rule("nutrition", "medium", re.compile(
        r"\b(fast food|weight (gain|issue)|out of shape|diet breach)\b", re.I
    )),
    Rule("nutrition", "low", re.compile(
        r"\b(restaurant|dinner|steakhouse|nutrition|diet)\b", re.I
    )),
    Rule("conflict", "high", re.compile(
        r"\b(transfer request|refused to (play|train)|dressing[- ]room row|"
        r"clash with (the )?coach|walked out)\b", re.I
    )),
    Rule("conflict", "medium", re.compile(
        r"\b(dispute|argument|fallout|unhappy with (the )?manager|"
        r"dropped after|squad unrest)\b", re.I
    )),
    Rule("rest", "low", re.compile(
        r"\b(rested|rotation|given a night off|recovery|sleep|day off|"
        r"managed minutes)\b", re.I
    ), polarity="positive"),
    Rule("readiness", "low", re.compile(
        r"\b(full training|sharp|available|fit to start|no issues|"
        r"came through training|raring to go|in contention)\b", re.I
    ), polarity="positive"),
]


_NEGATION = re.compile(
    r"\b(no|without|never|not a|n['’]t|rather than(?: an?)?|denies|denied)\b(?:\s+\w+){0,5}\s*$",
    re.I,
)


def _is_negated(text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 56):match.start()]
    return bool(_NEGATION.search(prefix))


def _window_around(text: str, match: re.Match[str], radius: int = 140) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    return snippet


def _player_near(snippet: str, player: Player) -> bool:
    blob = fold(snippet)
    for alias in player.aliases or [player.name]:
        token = fold(alias)
        if len(token) < 3:
            continue
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", blob):
            return True
    return False


def _best_severity(existing: Severity, incoming: Severity) -> Severity:
    return incoming if SEVERITY_RANK[incoming] > SEVERITY_RANK[existing] else existing


def analyze_text_for_player(
    player: Player,
    text: str,
    *,
    source_url: str | None,
    source_type: str,
    source_title: str | None,
    demo: bool = False,
    require_name: bool = True,
) -> list[Signal]:
    if not text:
        return []
    found: list[Signal] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            if rule.polarity == "negative" and _is_negated(text, match):
                continue
            snippet = _window_around(text, match)
            if require_name and not _player_near(snippet, player):
                # Some articles are exclusively about one player
                if require_name and player.name.lower() not in fold(text) and not any(
                    fold(a) in fold(text) for a in player.aliases
                ):
                    continue
                # If the player is mentioned in the document, still require local proximity
                # unless the document is short.
                if len(text) > 400 and not _player_near(snippet, player):
                    continue
            found.append(
                Signal(
                    player_id=player.id,
                    player_name=player.name,
                    category=rule.category,
                    severity=rule.severity,
                    evidence=snippet,
                    source_url=source_url,
                    source_type=source_type,  # type: ignore[arg-type]
                    source_title=source_title,
                    demo=demo,
                )
            )
    return _dedupe_signals(found)


def _dedupe_signals(signals: list[Signal]) -> list[Signal]:
    best: dict[tuple[str, str, str], Signal] = {}
    for signal in signals:
        key = (signal.player_id, signal.category, (signal.source_url or "")[:80])
        current = best.get(key)
        if current is None:
            best[key] = signal
            continue
        if SEVERITY_RANK[signal.severity] > SEVERITY_RANK[current.severity]:
            best[key] = signal
        elif signal.severity == current.severity and len(signal.evidence) > len(current.evidence):
            best[key] = signal
    return list(best.values())


def collect_player_text(player: Player, articles: list[Article], social: list[SocialItem]) -> str:
    chunks: list[str] = []
    for article in articles:
        if player.name in article.player_mentions:
            chunks.append(article.title)
            if article.full_text:
                chunks.append(article.full_text)
            elif article.snippet:
                chunks.append(article.snippet)
    for item in social:
        if item.player_id == player.id:
            chunks.append(item.content)
    return "\n".join(chunks)


def analyze_sources(
    players: list[Player],
    articles: list[Article],
    social: list[SocialItem],
) -> list[Signal]:
    signals: list[Signal] = []
    for article in articles:
        text = "\n".join(filter(None, [article.title, article.snippet, article.full_text]))
        mentioned = [p for p in players if p.name in article.player_mentions]
        if not mentioned:
            continue
        single = len(mentioned) == 1
        for player in mentioned:
            signals.extend(
                analyze_text_for_player(
                    player,
                    text,
                    source_url=article.url,
                    source_type="article",
                    source_title=article.title,
                    demo=article.demo,
                    require_name=not single,
                )
            )
    for item in social:
        player = next((p for p in players if p.id == item.player_id), None)
        if not player:
            continue
        source_type = "reported_social" if item.fetch_status == "second_hand" else "social"
        signals.extend(
            analyze_text_for_player(
                player,
                item.content,
                source_url=item.url,
                source_type=source_type,  # type: ignore[arg-type]
                source_title=f"{item.platform} {item.media_type}",
                demo=item.demo,
                require_name=False,
            )
        )
    return _dedupe_signals(signals)
