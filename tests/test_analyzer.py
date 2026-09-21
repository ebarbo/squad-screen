from __future__ import annotations

from squad_screen.analyzer.rules import analyze_sources, analyze_text_for_player
from squad_screen.models import Article, Player, SocialItem


def _player(name: str, pid: str = "1", position: str = "Forward") -> Player:
    return Player(
        id=pid,
        name=name,
        position=position,
        position_code="ST",
        source="test",
        aliases=[name.split()[-1]],
    )


def test_generic_injury_word_is_medium():
    player = _player("Ricardo Pepi", "9")
    text = "Ricardo Pepi's injury in PSV match a concern for USMNT."
    signals = analyze_text_for_player(
        player,
        text,
        source_url="https://example.test/pepi",
        source_type="article",
        source_title="test",
        require_name=False,
    )
    injuries = [s for s in signals if s.category == "injury"]
    assert injuries
    assert injuries[0].severity in {"medium", "high"}


def test_hamstring_is_medium_injury():
    player = _player("Ronald Araújo", "4")
    text = (
        "Ronald Araújo cut short training after hamstring tightness. "
        "A scan is scheduled. He is an injury doubt."
    )
    signals = analyze_text_for_player(
        player,
        text,
        source_url="https://example.test/araujo",
        source_type="article",
        source_title="test",
        require_name=True,
    )
    injuries = [s for s in signals if s.category == "injury"]
    assert injuries, signals
    assert any(s.severity in {"medium", "high"} for s in injuries)
    assert "hamstring" in injuries[0].evidence.lower()


def test_ruled_out_is_high_injury():
    player = _player("Dani Olmo", "20")
    text = "Barcelona have ruled out Dani Olmo after a muscle injury. He is sidelined."
    signals = analyze_text_for_player(
        player,
        text,
        source_url="https://example.test/olmo",
        source_type="article",
        source_title="test",
        require_name=False,
    )
    injuries = [s for s in signals if s.category == "injury"]
    assert any(s.severity == "high" for s in injuries)


def test_nightclub_medium_partying():
    player = _player("Alejandro Balde", "3")
    text = "Alejandro Balde was photographed in the VIP area of a nightclub until late."
    signals = analyze_text_for_player(
        player,
        text,
        source_url="https://example.test/balde",
        source_type="article",
        source_title="test",
        require_name=False,
    )
    cats = {s.category for s in signals}
    assert "late_night_partying" in cats


def test_rather_than_rupture_is_not_high_injury():
    player = _player("Ronald Araújo", "4")
    text = (
        "Teammates described the issue as a twinge rather than a rupture, "
        "but Ronald Araújo has hamstring tightness and is an injury doubt."
    )
    signals = analyze_text_for_player(
        player,
        text,
        source_url="https://example.test/araujo2",
        source_type="article",
        source_title="test",
        require_name=False,
    )
    injuries = [s for s in signals if s.category == "injury"]
    assert injuries
    assert all(s.severity != "high" for s in injuries)


def test_negated_fitness_test_is_not_an_injury():
    player = _player("Pedri", "8")
    text = "Pedri came through training without any fitness test required and is available."
    signals = analyze_text_for_player(
        player,
        text,
        source_url="https://example.test/pedri",
        source_type="article",
        source_title="test",
        require_name=False,
    )
    assert not any(s.category == "injury" for s in signals)


def test_does_not_invent_on_empty_text():
    player = _player("Pedri", "8")
    signals = analyze_text_for_player(
        player,
        "",
        source_url=None,
        source_type="article",
        source_title=None,
    )
    assert signals == []


def test_analyze_sources_uses_quotes_from_article_only():
    player = _player("Gavi", "6")
    article = Article(
        title="Gavi fatigue watch",
        url="https://example.test/gavi",
        source="Test",
        snippet="Staff want Gavi minutes management after signs of fatigue.",
        full_text="Coaching staff want Gavi's minutes managed after signs of fatigue in midweek.",
        player_mentions=["Gavi"],
    )
    signals = analyze_sources([player], [article], [])
    assert signals
    assert all("fatigue" in s.evidence.lower() or "minutes" in s.evidence.lower() for s in signals)
    assert all(s.source_url == article.url for s in signals)


def test_social_item_can_create_signal():
    player = _player("Jules Koundé", "23")
    social = SocialItem(
        platform="Instagram",
        author="kounde",
        content="Long day of travel. Delayed flight but home now.",
        player_id="23",
        player_name="Jules Koundé",
    )
    signals = analyze_sources([player], [], [social])
    assert any(s.category == "travel" for s in signals)
