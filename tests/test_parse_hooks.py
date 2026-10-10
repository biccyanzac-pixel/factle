from pipeline.parse_hooks import parse_line, parse_page, to_statement


def stmt(line):
    h = parse_line(line)
    assert h["problem"] is None, h
    return h["statement"]


def test_basic_hook():
    assert stmt("* ... that octopuses have three hearts?") == "Octopuses have three hearts."


def test_old_spacing_variants():
    assert stmt("*...that '''[[octopus]]es''' have three hearts?") == "Octopuses have three hearts."
    assert stmt("*... that '''[[Octopus|octopuses]]''' have three hearts?") == "Octopuses have three hearts."


def test_pictured_removed_and_flagged():
    h = parse_line("* ... that '''[[Ebony Stevenson]]''' ''(pictured)'' wore decorated footwear at the Games?")
    assert h["statement"] == "Ebony Stevenson wore decorated footwear at the Games."
    assert h["pictured"] is True


def test_links_and_bold():
    h = parse_line("* ... that '''[[Suga Shrine (Shinjuku)|a shrine]]'''{{`s}} staircase appears in ''[[Your Name]]''{{-?}}")
    assert h["statement"] == "A shrine's staircase appears in Your Name."
    assert h["links"] == [
        {"title": "Suga Shrine (Shinjuku)", "label": "a shrine", "bold": True},
        {"title": "Your Name", "label": "Your Name", "bold": False},
    ]


def test_templates():
    assert stmt("* ... that the tower is {{convert|200|m|ft|0}} tall?") == "The tower is 200 metres tall."
    assert stmt("* ... that it is a {{convert|200|m|ft|adj=on}} tower?") == "It is a 200-metre tower."
    assert stmt("* ... that {{HMS|Colchester|1744}} was built in Kent?") == "HMS Colchester was built in Kent."
    assert stmt("* ... that it sold for {{nowrap|$1 million}}?") == "It sold for $1 million."


def test_unknown_template_is_rejected_not_guessed():
    assert parse_line("* ... that it weighs {{mystery|4}}?")["problem"] == "template:mystery"


def test_lowercase_brand_kept():
    assert stmt("* ... that '''[[eBay]]''' was founded in 1995?") == "eBay was founded in 1995."


def test_that_with_comma_and_merged_hooks():
    assert stmt("* ... that, in 1936, the party won four seats?") == "In 1936, the party won four seats."
    assert to_statement("that A was built in 1941, and that B was built in 1942?")[0] == \
        "A was built in 1941, and B was built in 1942."


def test_quoted_question_rejected():
    assert to_statement('that he asked "why not?"')[1] == "ends_in_quoted_question"
    assert to_statement("that X happened")[1] == "no_question_mark"


def test_statement_ending_in_quote_gets_no_extra_period():
    assert stmt('* ... that a critic called it "a mountain castle."?') == 'A critic called it "a mountain castle."'


def test_comment_and_ref_removed():
    assert stmt("* ... that cats<!-- note --> purr<ref>x</ref>?") == "Cats purr."


def test_parse_page_dates():
    text = "===9 October 2026===\n*'''''00:00, 9 October 2026 (UTC)'''''\n* ... that cats purr?\n"
    (h,) = list(parse_page(text))
    assert h["ran"] == "2026-10-09T00:00Z"
