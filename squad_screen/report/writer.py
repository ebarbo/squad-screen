from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from squad_screen.models import Report

SEVERITY_BADGE = {"low": "LOW", "medium": "MED", "high": "HIGH"}


def _dt(value: datetime | None) -> str:
    if value is None:
        return "unknown date"
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def render_markdown(report: Report) -> str:
    team = report.team.name
    mode = "DEMO DATA — not a live collection" if report.mode == "demo" else "LIVE collection"
    lines: list[str] = [
        f"# Squad Screen — {team}",
        "",
        f"**Mode:** {mode}  ",
        f"**Window:** {_dt(report.window_start)} → {_dt(report.window_end)}  ",
        f"**Generated:** {_dt(report.generated_at)}  ",
        f"**Roster source:** {report.team.source} ({len(report.roster)} players)",
        "",
        "## Match-day recommendation",
        "",
        report.lineup.summary,
        "",
        f"### Starting XI ({report.lineup.formation})",
        "",
    ]
    if not report.lineup.starting_xi:
        lines.append("_No eleven could be named (roster missing or everyone flagged rest)._")
    for slot in report.lineup.starting_xi:
        num = f"#{slot.player.shirt_number} " if slot.player.shirt_number else ""
        lines.append(f"- **{slot.slot}** {num}{slot.player.name} — {slot.rationale}")
    lines += ["", "### Bench", ""]
    if not report.lineup.bench:
        lines.append("_No bench named._")
    for slot in report.lineup.bench:
        num = f"#{slot.player.shirt_number} " if slot.player.shirt_number else ""
        lines.append(
            f"- {num}{slot.player.name} ({slot.player.position or slot.slot}, {slot.recommended_role}) — {slot.rationale}"
        )
    lines += ["", "### Rest / unavailable", ""]
    if not report.lineup.rest:
        lines.append("_None flagged for rest._")
    for slot in report.lineup.rest:
        lines.append(f"- {slot.player.name} — {slot.rationale}")
    if report.lineup.rotation_notes:
        lines += ["", "### Rotation notes", ""]
        for note in report.lineup.rotation_notes:
            lines.append(f"- {note}")

    lines += ["", "## Per-player assessments", ""]
    for assessment in sorted(
        report.assessments,
        key=lambda a: (a.recommended_role != "rest", a.player_name),
    ):
        lines += [
            f"### {assessment.player_name}",
            "",
            f"- Position: {assessment.position or 'unknown'} (`{assessment.position_code or '?'}`)",
            f"- Recommended role: **{assessment.recommended_role}**",
            f"- Estimated performance impact: {assessment.estimated_impact}",
            f"- Injury risk: {assessment.injury_risk}",
            f"- Media mentions in window: {assessment.mention_count}",
            f"- Rationale: {assessment.rationale}",
            "",
        ]

    lines += ["", "## Signals", ""]
    if not report.signals:
        lines.append("_No lifestyle or medical signals were extracted from collected material._")
    else:
        for signal in report.signals:
            badge = SEVERITY_BADGE[signal.severity]
            url = f" ([source]({signal.source_url}))" if signal.source_url else ""
            demo = " · demo" if signal.demo else ""
            lines += [
                f"- **{signal.player_name}** — `{signal.category}` · {badge}{demo}{url}",
                f"  - Evidence: “{signal.evidence}”",
            ]

    lines += ["", "## Articles", ""]
    if not report.articles:
        lines.append("_No articles collected in this window._")
    else:
        for article in report.articles:
            when = _dt(article.published_at)
            status = article.fetch_status
            if article.paywalled:
                status += ", paywalled"
            mentions = ", ".join(article.player_mentions) or "team-level"
            demo = " · demo" if article.demo else ""
            lines += [
                f"- **{article.title}** — {article.source} · {when}{demo}",
                f"  - {article.url}",
                f"  - Status: {status}; players: {mentions}",
            ]
            if article.snippet:
                lines.append(f"  - Snippet: {article.snippet[:280]}")

    lines += ["", "## Social items", ""]
    if not report.social_items:
        lines.append("_No social items collected._")
    else:
        grouped: dict[str, list] = {}
        for item in report.social_items:
            grouped.setdefault(item.platform, []).append(item)
        preferred = ("Instagram", "X")
        platforms = [name for name in preferred if name in grouped]
        platforms.extend(name for name in grouped if name not in preferred)
        for platform in platforms:
            lines += [f"### {platform}", ""]
            for item in grouped[platform]:
                when = _dt(item.timestamp)
                demo = " · demo" if item.demo else ""
                link = f" — {item.url}" if item.url else ""
                lines += [
                    f"- **{item.player_name}** · {item.platform} {item.media_type} · {when} · {item.fetch_status}{demo}{link}",
                    f"  - {item.content[:400]}",
                ]
            lines.append("")

    lines += ["", "## Roster", ""]
    for player in report.roster:
        num = f"#{player.shirt_number} " if player.shirt_number is not None else ""
        lines.append(
            f"- {num}{player.name} — {player.position or 'unknown'} ({player.position_code or '?'}) · {player.source}"
        )

    lines += ["", "## Coverage gaps", ""]
    if not report.coverage_gaps:
        lines.append("_No gaps recorded._")
    for gap in report.coverage_gaps:
        lines += [
            f"- **{gap.area}** — {gap.reason}",
            f"  - Impact: {gap.impact}",
        ]

    lines += ["", "## Sources attempted", ""]
    for source in report.sources_attempted:
        lines.append(f"- {source}")

    if report.notes:
        lines += ["", "## Notes", ""]
        for note in report.notes:
            lines.append(f"- {note}")

    lines.append("")
    return "\n".join(lines)


def write_report(report: Report, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    slug = report.team.name.lower().replace(" ", "_")
    stem = f"{stamp}_{slug}_{report.mode}"
    md_path = directory / f"{stem}.md"
    json_path = directory / f"{stem}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (directory / "latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    (directory / "latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    return md_path, json_path


def report_to_dict(report: Report) -> dict:
    return json.loads(report.model_dump_json())
