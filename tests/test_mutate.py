import random

from pipeline import mutate


def fact(statement, entities=(), ran="2020-01-01T00:00Z"):
    return {"statement": statement, "entities": list(entities), "ran": ran, "sources": [], "words": len(statement.split())}


def ent(s, text, label):
    i = s.index(text)
    return {"text": text, "label": label, "start": i, "end": i + len(text)}


def all_mutations(f, n=40, pools=None, kinds=None):
    out = []
    for seed in range(n):
        out += mutate.candidates(f, random.Random(seed), pools or {"nation": []}, kinds or {})
    return out


def test_year_shift_keeps_order_and_not_future():
    s = "The sawmill was built in 1862 and remained in operation until 1989."
    f = fact(s, [ent(s, "1862", "DATE"), ent(s, "1989", "DATE")], ran="2010-05-01T00:00Z")
    for m in all_mutations(f):
        assert m["kind"] == "year"
        new = int(m["new"])
        if m["old"] == "1862":
            assert new < 1989
        else:
            assert 1862 < new <= 2010
        assert m["fake"].count(m["new"]) == 1


def test_count_scaled_and_formatted():
    s = "After buying a camera in the 1880s, she took over 30,000 photographs."
    f = fact(s, [ent(s, "30,000", "CARDINAL"), ent(s, "the 1880s", "DATE")])
    counts = [m for m in all_mutations(f) if m["kind"] == "count"]
    assert counts
    for m in counts:
        v = int(m["new"].replace(",", ""))
        assert v != 30000 and v >= 2 and "," in m["new"]
        assert v % 1000 == 0  # a round number stays round


def test_decade_shift():
    s = "After buying a camera in the 1880s, she took many photographs of the town."
    f = fact(s, [ent(s, "the 1880s", "DATE")])
    ms = all_mutations(f)
    assert ms and all(m["new"].endswith("0s") and m["new"] != "1880s" for m in ms)


def test_count_order_with_other_numbers():
    s = "Roy scored 60 goals during his career, 51 of which were penalties."
    f = fact(s, [ent(s, "60", "CARDINAL"), ent(s, "51", "CARDINAL")])
    for m in all_mutations(f):
        if m["old"] == "51":
            assert int(m["new"]) < 60
        if m["old"] == "60":
            assert int(m["new"]) > 51


def test_number_inside_name_untouched():
    s = "The episode of Inside No. 9 was filmed at 135 East 57th Street in 2014."
    f = fact(s, [ent(s, "Inside No. 9", "WORK_OF_ART"), ent(s, "135 East 57th Street", "FAC"), ent(s, "2014", "DATE")])
    ms = all_mutations(f)
    assert ms and all(m["old"] == "2014" for m in ms)


def test_percent_stays_at_most_100():
    s = "Bats comprise about 40% of all mammal species found in the range."
    f = fact(s, [ent(s, "about 40%", "PERCENT")])
    for m in all_mutations(f):
        assert int(m["new"]) <= 100


def test_article_fixed():
    s = "The club signed an 18-year-old goalkeeper from the reserve team."
    f = fact(s, [ent(s, "18-year-old", "DATE")])
    for m in all_mutations(f):
        fake = m["fake"]
        new = m["new"]
        want = "an" if new.startswith(("8", "11", "18")) and not new.startswith(("110", "180")) else "a"
        assert f" {want} {new}" in fake, fake


def test_nationality_swap_only_with_single_place():
    s = "Finnish lyricist Vexi Salmi wrote over 4000 song lyrics in his career."
    f = fact(s, [ent(s, "Finnish", "NORP"), ent(s, "Vexi Salmi", "PERSON"), ent(s, "over 4000", "CARDINAL")])
    pools = {"nation": ["Finnish", "Swedish", "Polish"]}
    ms = [m for m in all_mutations(f, pools=pools) if m["kind"] == "nation"]
    assert ms and all(m["new"] in ("Swedish", "Polish") for m in ms)
    s2 = "Polish jurist Józef Wybicki wrote the national anthem of Poland."
    f2 = fact(s2, [ent(s2, "Polish", "NORP"), ent(s2, "Poland", "GPE")])
    assert not [m for m in all_mutations(f2, pools=pools) if m["kind"] == "nation"]


def test_never_swaps_people():
    s = "Painter John Smith moved to Paris with his twelve cats and a parrot."
    f = fact(s, [ent(s, "John Smith", "PERSON"), ent(s, "Paris", "GPE"), ent(s, "twelve", "CARDINAL")])
    for m in all_mutations(f, pools={"nation": [], "country": ["France", "Italy"]}, kinds={"Paris": "city"}):
        assert "John Smith" in m["fake"]


def test_no_negation_added():
    s = "The bridge has three arches and was opened in 1890 by the mayor."
    f = fact(s, [ent(s, "three", "CARDINAL"), ent(s, "1890", "DATE")])
    for m in all_mutations(f):
        assert not mutate.NEGATION_RE.search(m["fake"])


def test_ranges_names_and_untagged_years_untouched():
    s = "Small Heath won the inaugural Second Division title in 1892–93 at 18 Broad Street with over 2000 fans."
    f = fact(s, [ent(s, "1892–93", "DATE"), ent(s, "over 2000", "CARDINAL")])
    ms = all_mutations(f)
    assert all(m["old"] == "2000" and m["kind"] == "count" for m in ms)


def test_religion_is_not_a_nationality():
    s = "Catholic priest Herbert Leuninger co-founded a refugee charity in Frankfurt."
    f = fact(s, [ent(s, "Catholic", "NORP")])
    assert not [m for m in all_mutations(f, pools={"nation": ["Catholic", "Asian"]}) if m["kind"] == "nation"]


def test_three_digit_year_shifted_as_year():
    s = "At the end of the Siege of Kiev in 968, the leaders shook hands."
    f = fact(s, [ent(s, "968", "DATE")])
    ms = all_mutations(f)
    assert ms and all(m["kind"] == "year" and 100 <= int(m["new"]) < 1000 for m in ms)


def test_relay_and_adjective_country_untouched():
    s = "Norway lost the 4 x 10 km relay at its United States premiere in 1994."
    f = fact(s, [ent(s, "United States", "GPE"), ent(s, "1994", "DATE")])
    ms = all_mutations(f, pools={"nation": [], "country": ["United States", "Greece"]}, kinds={"United States": "country"})
    assert ms and all(m["old"] == "1994" for m in ms)


def test_uk_nationalities_never_swap_with_each_other():
    s = "P. T. Barnum named English showman Tom Norman the Silver King in 1880."
    f = fact(s, [ent(s, "English", "NORP"), ent(s, "1880", "DATE")])
    for m in all_mutations(f, pools={"nation": ["English", "British", "Scottish", "French"]}):
        if m["kind"] == "nation":
            assert m["new"] == "French"
