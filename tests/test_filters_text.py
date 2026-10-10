import pytest

from pipeline.filters_text import check


@pytest.mark.parametrize("s", [
    "Octopuses have three hearts and blue blood in their arteries.",  # 'blood' -> unsuitable, see below
])
def test_blood_is_blocked(s):
    assert check(s) == "unsuitable_topic"


@pytest.mark.parametrize("s", [
    "The Western Australian shrubs Persoonia elliptica and Persoonia saccata are known as snottygobbles.",
    "The beaded sea cucumber moves by means of peristalsis.",
    "In 1890 the bridge was the longest in Europe.",  # historical superlative with a date
    "Star Wars was filmed partly in Tunisia in 1976.",
])
def test_kept(s):
    assert check(s) is None


@pytest.mark.parametrize("s,reason", [
    ("The town currently has three bakeries and a small museum.", "fast_changing"),
    ("The tree is the oldest oak in the whole of England.", "fast_changing"),
    ("The bridge was the longest in Europe.", "fast_changing"),  # superlative without a date
    ("The village has a population of 300 people and two churches.", "fast_changing"),
    ("The ticket costs $5 at the museum gift shop.", "fast_changing"),
    ("The battle killed forty men in the rain.", "unsuitable_topic"),
    ("The ship sank in 1912, and many people died.", "unsuitable_topic"),
    ("He wrote three novels while living in a lighthouse.", "needs_context"),
    ("This building was designed by a twelve-year-old girl.", "needs_context"),
    ("The album was released last year on vinyl only.", "needs_context"),
    ("Cats purr.", "too_short"),
    (" ".join(["word"] * 31), "too_long"),
])
def test_rejected(s, reason):
    assert check(s) == reason


def test_link_titles_are_checked_for_topic():
    assert check("The site was visited by forty people in 1602.", ["Murder of Thomas Becket"]) == "unsuitable_topic"


def test_aids_only_as_disease():
    assert check("The charity raised funds for AIDS research in 1990.") == "unsuitable_topic"
    assert check("The device aids navigation on small boats in 1990.") is None
