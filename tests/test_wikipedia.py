from squad_screen.names import normalize_position
from squad_screen.roster.wikipedia import parse_squad_tables


HTML = """
<h2>Current squad</h2>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Nation</th><th>Player</th></tr>
<tr><td>1</td><td>GK</td><td>ESP</td><td>Joan Garcia</td></tr>
<tr><td>8</td><td>MF</td><td>ESP</td><td>Pedri ( vice-captain )</td></tr>
<tr><td>10</td><td>FW</td><td>ESP</td><td>Lamine Yamal</td></tr>
</table>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Nation</th><th>Player</th></tr>
<tr><td>21</td><td>MF</td><td>NED</td><td>Frenkie de Jong</td></tr>
<tr><td>23</td><td>DF</td><td>FRA</td><td>Jules Koundé</td></tr>
</table>
<h2>Out on loan</h2>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Nation</th><th>Player</th></tr>
<tr><td>—</td><td>GK</td><td>GER</td><td>Marc-André ter Stegen (at Ajax)</td></tr>
</table>
"""


def test_wikipedia_merges_current_squad_and_skips_loans():
    players = parse_squad_tables(HTML, "FC Barcelona")
    names = {p.name for p in players}
    assert "Pedri" in names
    assert "Jules Koundé" in names
    assert "Marc-André ter Stegen" not in names
    joan = next(p for p in players if p.name == "Joan Garcia")
    assert joan.position_code == "GK"
    assert joan.shirt_number == 1
    kounde = next(p for p in players if "Koundé" in p.name)
    assert kounde.position_code == "CB"


def test_date_rows_are_not_players():
    html = """
    <h2>Current squad</h2>
    <table class="wikitable">
    <tr><th>No.</th><th>Pos.</th><th>Player</th></tr>
    <tr><td>1</td><td>GK</td><td>Joan Garcia</td></tr>
    <tr><td></td><td></td><td>27 August 2026</td></tr>
    </table>
    """
    players = parse_squad_tables(html, "x")
    assert [p.name for p in players] == ["Joan Garcia"]


def test_df_mf_fw_codes():
    assert normalize_position("DF") == "CB"
    assert normalize_position("MF") == "CM"
    assert normalize_position("FW") == "ST"
    assert normalize_position("GK") == "GK"
