from app.search.nlq import parse_rules


def test_full_query_en():
    f, chips = parse_rules("olympic triathlon in germany in may with wetsuit allowed, flat course")
    assert f.sport == ["triathlon"] and f.discipline == ["olympic"] and f.country == ["DE"]
    assert f.date_from and f.date_from.month == 5 and f.date_to.month == 6
    keys = {a.key for a in f.attributes}
    assert keys == {"wetsuit_rule", "course_profile"}
    assert f.q is None
    assert len(chips) >= 4


def test_query_de_near_city_and_price():
    f, _ = parse_rules("halbmarathon nähe münchen im herbst unter 50 €")
    assert f.discipline == ["half-marathon"] and f.sport == ["running"]
    assert f.near_lat and f.radius_km == 75
    assert f.price_max == 50
    assert f.date_from.month == 9


def test_leftover_goes_to_q():
    f, _ = parse_rules("Langdistanz Kärnten")
    assert f.discipline == ["long"]
    assert f.q == "kärnten"


def test_registration_open_and_relay():
    f, _ = parse_rules("sprint triathlon staffel anmeldung offen")
    assert f.relay is True and f.reg_state == ["open"]
