from squad_screen.models import Player
from squad_screen.news import match_players


def test_dennis_man_does_not_match_manchester_united():
    player = Player(
        id="27",
        name="Dennis Man",
        position="FW",
        position_code="ST",
        source="test",
        aliases=["Dennis Man", "Man"],
    )
    assert match_players("Manchester United drew at Fulham", [player]) == []
    assert match_players("Man City beat Sunderland", [player]) == []
    assert match_players("Dennis Man scored for PSV Eindhoven", [player]) == ["Dennis Man"]
