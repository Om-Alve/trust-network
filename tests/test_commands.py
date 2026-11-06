"""Tests for the gate command parser: PLAN.md §3 and §4, plus sloppy input."""

from datetime import date, datetime, timedelta

import pytest

from trustnet.gate.commands import (
    EXAMPLES,
    IST,
    MAX_PLACE,
    MAX_QUESTION,
    MAX_TITLE,
    Answer,
    Ask,
    AskAround,
    AskOwner,
    Claim,
    Consent,
    Counter,
    Dm,
    Free,
    GiftIdeas,
    JoinDm,
    Ledger,
    No,
    ParseError,
    Propose,
    Quoted,
    Trust,
    Unknown,
    ViewAs,
    Yes,
    parse,
)
from trustnet.gate.facts import Level

# Thursday 5 November 2026, 09:00 IST. The demo outing is Sunday the 8th.
NOW = datetime(2026, 11, 5, 9, 0, tzinfo=IST)
OUTING = datetime(2026, 11, 8, 21, 0, tzinfo=IST)
PLACE = "Smaaash, Indiranagar"


def p(text: str) -> object:
    return parse(text, now=NOW)


# Every literal command line in PLAN.md §3 (both lists).
PLAN_SECTION_3 = [
    (
        "@om-gate free 2026-11-08..2026-11-09",
        Free(date(2026, 11, 8), date(2026, 11, 9), target="om-gate"),
    ),
    ("@om-gate ask diet interests", Ask(("diet", "interests"), target="om-gate")),
    (
        '@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"',
        AskOwner("Q3", Quoted("Is ₹1,500 per person okay?"), target="om-gate"),
    ),
    (
        '@om-gate propose P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"',
        Propose(
            "P1",
            OUTING,
            timedelta(hours=2),
            "Bowling + dinner",
            PLACE,
            target="om-gate",
        ),
    ),
    (
        '@om-gate counter P1 P2 2026-11-09T19:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"',
        Counter(
            "P1",
            "P2",
            datetime(2026, 11, 9, 19, 0, tzinfo=IST),
            timedelta(hours=2),
            "Bowling + dinner",
            PLACE,
            target="om-gate",
        ),
    ),
    (
        "@om-gate gift-ideas birthday 2026-11-20 budget<=3000",
        GiftIdeas("birthday", date(2026, 11, 20), 3000, target="om-gate"),
    ),
    ('@om-gate claim "Lego Millennium Falcon"', Claim("Lego Millennium Falcon", target="om-gate")),
    (
        '@om-gate ask-around "tent to borrow, Nov 14-16"',
        AskAround(Quoted("tent to borrow, Nov 14-16"), target="om-gate"),
    ),
    (
        '@om-gate dm rahul "something fun Sunday evening, not pricey"',
        Dm(
            "rahul",
            Quoted("something fun Sunday evening, not pricey"),
            target="om-gate",
        ),
    ),
    (
        '@om-gate ask-around "anyone have a tent for Nov 14-16?"',
        AskAround(Quoted("anyone have a tent for Nov 14-16?"), target="om-gate"),
    ),
    ("@om-gate yes P1", Yes("P1", target="om-gate")),
    ("@om-gate no P1", No("P1", target="om-gate")),
    (
        '@om-gate answer Q3 "yes, up to ₹1,500"',
        Answer("Q3", Quoted("yes, up to ₹1,500"), target="om-gate"),
    ),
    ("@om-gate trust priya close", Trust("priya", Level.CLOSE, target="om-gate")),
    ("@om-gate view-as rahul", ViewAs("rahul", target="om-gate")),
    ("@om-gate ledger", Ledger(target="om-gate")),
]

# Every literal command line in PLAN.md §4 (the two propose lines end in "…"
# there, so their full form is the §3 example above).
PLAN_SECTION_4 = [
    (
        '@om-gate dm rahul "something fun Sunday evening, not pricey"',
        Dm(
            "rahul",
            Quoted("something fun Sunday evening, not pricey"),
            target="om-gate",
        ),
    ),
    (
        '@rahul-gate ask-owner Q1 "Is ₹1,500 per person okay?"',
        AskOwner("Q1", Quoted("Is ₹1,500 per person okay?"), target="rahul-gate"),
    ),
    ("@om-gate yes P1", Yes("P1", target="om-gate")),
    (
        "@om-gate gift-ideas birthday 2026-11-20 budget<=3000",
        GiftIdeas("birthday", date(2026, 11, 20), 3000, target="om-gate"),
    ),
    ("@om-gate ledger", Ledger(target="om-gate")),
    (
        '@om-gate ask-around "tent to borrow, Nov 14-16"',
        AskAround(Quoted("tent to borrow, Nov 14-16"), target="om-gate"),
    ),
    ("@om-gate view-as rahul", ViewAs("rahul", target="om-gate")),
]


@pytest.mark.parametrize(("text", "expected"), PLAN_SECTION_3 + PLAN_SECTION_4)
def test_every_plan_command_line_parses(text: str, expected: object) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Case, spacing and fences.
        (
            "@om-gate Free 2026-11-08..2026-11-09",
            Free(date(2026, 11, 8), date(2026, 11, 9), target="om-gate"),
        ),
        (
            "  @om-gate   free   2026-11-08 .. 2026-11-09  ",
            Free(date(2026, 11, 8), date(2026, 11, 9), target="om-gate"),
        ),
        (
            "```\n@om-gate free 2026-11-08..2026-11-09\n```",
            Free(date(2026, 11, 8), date(2026, 11, 9), target="om-gate"),
        ),
        (
            "@om-gate free 2026-11-08..2026-11-09.",
            Free(date(2026, 11, 8), date(2026, 11, 9), target="om-gate"),
        ),
        # No @gate prefix at all.
        (
            "free 2026-11-08..2026-11-09",
            Free(date(2026, 11, 8), date(2026, 11, 9)),
        ),
        # Natural-language ranges.
        ("@om-gate free Nov 14-16", Free(date(2026, 11, 14), date(2026, 11, 16), target="om-gate")),
        (
            "@om-gate free Nov 14 to 16",
            Free(date(2026, 11, 14), date(2026, 11, 16), target="om-gate"),
        ),
        (
            "@om-gate free Nov 14–16",
            Free(date(2026, 11, 14), date(2026, 11, 16), target="om-gate"),
        ),
        (
            "@om-gate free 2026-11-14..16",
            Free(date(2026, 11, 14), date(2026, 11, 16), target="om-gate"),
        ),
        (
            "@om-gate free 14-16 Nov",
            Free(date(2026, 11, 14), date(2026, 11, 16), target="om-gate"),
        ),
        ("@om-gate free Sunday", Free(date(2026, 11, 8), date(2026, 11, 8), target="om-gate")),
        # Missing quotes around one-word title and place; relative date+time.
        (
            "@om-gate propose P1 Sun 9pm 2h Bowling @ Smaaash",
            Propose(
                "P1",
                OUTING,
                timedelta(hours=2),
                "Bowling",
                "Smaaash",
                target="om-gate",
            ),
        ),
        (
            "@om-gate propose p1 2026-11-09 19:00 90m Dinner @ Toit",
            Propose(
                "P1",
                datetime(2026, 11, 9, 19, 0, tzinfo=IST),
                timedelta(minutes=90),
                "Dinner",
                "Toit",
                target="om-gate",
            ),
        ),
        (
            '@om-gate propose P1 2026-11-08T21:00 1h30m "Bowling" @ "Smaaash"',
            Propose(
                "P1",
                OUTING,
                timedelta(minutes=90),
                "Bowling",
                "Smaaash",
                target="om-gate",
            ),
        ),
        # Smart quotes.
        (
            "@om-gate propose P1 2026-11-08T21:00 2h “Bowling + dinner” @ “Smaaash, Indiranagar”",
            Propose(
                "P1",
                OUTING,
                timedelta(hours=2),
                "Bowling + dinner",
                PLACE,
                target="om-gate",
            ),
        ),
        # A trailing full stop after the closing quote.
        (
            '@om-gate propose P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar".',
            Propose(
                "P1",
                OUTING,
                timedelta(hours=2),
                "Bowling + dinner",
                PLACE,
                target="om-gate",
            ),
        ),
        # Budget spellings.
        (
            "@om-gate gift-ideas birthday 2026-11-20 budget 3000",
            GiftIdeas("birthday", date(2026, 11, 20), 3000, target="om-gate"),
        ),
        (
            "@om-gate gift-ideas Birthday Nov 20 ₹3,000",
            GiftIdeas("birthday", date(2026, 11, 20), 3000, target="om-gate"),
        ),
        (
            "@om-gate gift-ideas birthday Nov 20",
            GiftIdeas("birthday", date(2026, 11, 20), None, target="om-gate"),
        ),
        # Commas between facts; unquoted answers and claims; lowercase IDs.
        ("@om-gate ask Diet, Interests", Ask(("diet", "interests"), target="om-gate")),
        (
            "@om-gate ask-owner q3 Is ₹1,500 per person okay?",
            AskOwner("Q3", Quoted("Is ₹1,500 per person okay?"), target="om-gate"),
        ),
        (
            "@om-gate answer q3 yes, up to ₹1,500",
            Answer("Q3", Quoted("yes, up to ₹1,500"), target="om-gate"),
        ),
        (
            "@om-gate answer P1 yes",
            Answer("P1", Quoted("yes"), target="om-gate"),
        ),
        (
            "@om-gate claim Lego Millennium Falcon",
            Claim("Lego Millennium Falcon", target="om-gate"),
        ),
        ("@om-gate yes p1", Yes("P1", target="om-gate")),
        ("@om-gate no p2", No("P2", target="om-gate")),
        ("@om-gate trust Priya Close", Trust("priya", Level.CLOSE, target="om-gate")),
        ("@om-gate view-as Rahul", ViewAs("rahul", target="om-gate")),
        ("@om-gate   ledger.  ", Ledger(target="om-gate")),
        ("@om-gate ledger?", Ledger(target="om-gate")),
        # Gate-to-gate commands (phase 14/15).
        (
            '@rahul-gate join-dm dm-om-rahul-sun "something fun Sunday evening"',
            JoinDm(
                "dm-om-rahul-sun",
                Quoted("something fun Sunday evening"),
                target="rahul-gate",
            ),
        ),
        (
            "@rahul-gate consent P1 yes via-agent",
            Consent("P1", True, "via-agent", target="rahul-gate"),
        ),
        (
            "@om-gate consent P1 no direct",
            Consent("P1", False, "direct", target="om-gate"),
        ),
    ],
)
def test_sloppy_variants_parse(text: str, expected: object) -> None:
    assert p(text) == expected


def test_every_example_is_a_working_command() -> None:
    for command, example in EXAMPLES.items():
        parsed = p(example)
        assert not isinstance(parsed, Unknown), command
        assert type(parsed).__name__.lower().replace("-", "") == command.replace("-", "")


def test_relative_dates_follow_the_injected_clock() -> None:
    text = "@om-gate propose P1 Sat 9pm 2h Bowling @ Smaaash"

    first = parse(text, now=NOW)
    later = parse(text, now=datetime(2026, 11, 10, 9, 0, tzinfo=IST))

    assert isinstance(first, Propose)
    assert isinstance(later, Propose)
    assert first.start == datetime(2026, 11, 7, 21, 0, tzinfo=IST)
    assert later.start == datetime(2026, 11, 14, 21, 0, tzinfo=IST)


def test_the_outing_day_is_a_sunday() -> None:
    parsed = p("@om-gate free Sunday")

    assert isinstance(parsed, Free)
    assert parsed.start == date(2026, 11, 8)
    assert parsed.start.weekday() == 6


def test_boundary_questions_are_quoted_data() -> None:
    cases = {
        '@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"': "question",
        '@om-gate ask-around "tent to borrow"': "question",
        '@om-gate dm rahul "something fun"': "goal",
        '@om-gate answer Q3 "yes"': "text",
        '@rahul-gate join-dm dm-om-rahul-sun "goal"': "goal",
    }

    for text, attribute in cases.items():
        parsed = p(text)
        value = getattr(parsed, attribute)
        assert isinstance(value, Quoted), text
        assert str(value) == f'"{value.text}"'


def test_quoted_text_is_validated_on_its_own() -> None:
    assert Quoted("  hello  ").text == "hello"
    assert str(Quoted("hello")) == '"hello"'
    assert Quoted("hello").render() == '"hello"'

    with pytest.raises(ValueError, match="empty"):
        Quoted("   ")
    with pytest.raises(ValueError, match="double quote"):
        Quoted('say "this"')
    with pytest.raises(ValueError, match=str(MAX_QUESTION)):
        Quoted("x" * (MAX_QUESTION + 1))


def test_text_the_tools_quote_is_text_the_gate_accepts() -> None:
    """Tools build gate lines with ``Quoted``; the gate re-parses them.

    Ways the round trip can break: smart quotes pass the tool's check but turn
    into ``"`` in the gate's normaliser, so the gate answers "Invalid command"
    after the tool reported success; non-breaking or repeated spaces collapse
    in the gate, so the gate's text differs from what the tool sent.
    """
    dictated = [
        "Rahul: “Free for dinner Sunday after cricket.” Suggest a place",
        "Om‘s „idea“: bowling then  dinner",
        "plain words, nothing fancy",
    ]
    lines = {
        "goal": "@om-gate dm rahul {}",
        "question": "@om-gate ask-around {}",
        "text": "@om-gate answer Q3 {}",
    }

    for text in dictated:
        quoted = Quoted(text)
        for attribute, template in lines.items():
            parsed = p(template.format(quoted))
            assert getattr(parsed, attribute) == quoted, (template, text)


def test_limits_are_inclusive_at_the_boundary() -> None:
    title = "x" * MAX_TITLE
    place = "A" * MAX_PLACE
    question = "q" * MAX_QUESTION

    propose = p(f'@om-gate propose P1 2026-11-08T21:00 2h "{title}" @ "{place}"')
    ask = p(f'@om-gate ask-around "{question}"')

    assert isinstance(propose, Propose)
    assert len(propose.title) == MAX_TITLE
    assert len(propose.place) == MAX_PLACE
    assert isinstance(ask, AskAround)
    assert len(ask.question.text) == MAX_QUESTION


BAD_COMMANDS = [
    # Over-length title, place and question.
    f'@om-gate propose P1 2026-11-08T21:00 2h "{"x" * (MAX_TITLE + 1)}" @ "Smaaash"',
    f'@om-gate propose P1 2026-11-08T21:00 2h "Bowling" @ "{"A" * (MAX_PLACE + 1)}"',
    f'@om-gate ask-around "{"q" * (MAX_QUESTION + 1)}"',
    f'@om-gate dm rahul "{"q" * (MAX_QUESTION + 1)}"',
    # Characters the place rule forbids.
    '@om-gate propose P1 2026-11-08T21:00 2h "Bowling" @ "Café Roma"',
    '@om-gate propose P1 2026-11-08T21:00 2h "Bowling" @ "Cafe @ Home"',
    # Bad IDs, durations, levels and forms.
    '@om-gate propose Pone 2026-11-08T21:00 2h "Bowling" @ "Smaaash"',
    '@om-gate propose P1 someday 2h "Bowling" @ "Smaaash"',
    '@om-gate propose P1 2026-11-08T21:00 "Bowling" @ "Smaaash"',
    '@om-gate propose P1 2026-11-08T21:00 0h "Bowling" @ "Smaaash"',
    '@om-gate propose P1 2026-11-08T21:00 25h "Bowling" @ "Smaaash"',
    '@om-gate counter P1 2026-11-08T21:00 2h "Bowling" @ "Smaaash"',
    "@om-gate trust priya private",
    "@om-gate trust priya buddy",
    "@om-gate trust priya",
    "@om-gate view-as",
    "@om-gate view-as rahul priya",
    "@om-gate yes",
    "@om-gate no Px",
    "@om-gate ledger now",
    "@om-gate ask",
    "@om-gate ask diet, 9lives",
    "@om-gate ask-owner Is this okay?",
    '@om-gate ask-owner Q3 ""',
    '@om-gate answer Q3 ""',
    '@om-gate claim ""',
    '@om-gate claim "Lego Millennium Falcon" extra',
    "@om-gate dm",
    '@om-gate join-dm dm-om-rahul-sun ""',
    "@om-gate consent P1 maybe direct",
    "@om-gate consent P1 yes",
    "@om-gate free someday",
    "@om-gate gift-ideas birthday",
    "@om-gate gift-ideas birthday 2026-11-20 budget<=0",
]


@pytest.mark.parametrize("text", BAD_COMMANDS)
def test_bad_commands_raise_a_parse_error_with_a_working_example(text: str) -> None:
    with pytest.raises(ParseError) as info:
        p(text)

    example = info.value.example
    assert example
    assert example in str(info.value)
    assert not isinstance(p(example), Unknown)


@pytest.mark.parametrize(
    "text",
    [
        "@om-gate tell me a joke",
        "@om-gate freeform 2026-11-08",
        "hello there",
        "",
        "@om-gate",
        "   ",
    ],
)
def test_unknown_commands_keep_the_raw_text(text: str) -> None:
    parsed = p(text)

    assert isinstance(parsed, Unknown)
    assert parsed.raw == text.strip()


def test_unknown_keeps_the_addressed_gate() -> None:
    parsed = p("@om-gate tell me a joke")

    assert isinstance(parsed, Unknown)
    assert parsed.target == "om-gate"
    assert parsed.raw == "@om-gate tell me a joke"


def test_non_commands_inside_a_fence_are_unknown() -> None:
    assert isinstance(p("```\njust chatting\n```"), Unknown)
