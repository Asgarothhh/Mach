import time

import pytest

from app.orchestrator.turn_router import (
    SocialAct,
    TurnKind,
    route_turn,
    social_prefix,
    social_reply,
)


@pytest.mark.parametrize(
    ("text", "act"),
    [
        ("привет", SocialAct.GREETING),
        ("Здравствуйте!", SocialAct.GREETING),
        ("добрый день", SocialAct.GREETING),
        ("алло", SocialAct.GREETING),
        ("спасибо", SocialAct.THANKS),
        ("спасибо большое, всё понятно", SocialAct.THANKS),
        ("благодарю", SocialAct.THANKS),
        ("спасибо вы мне очень помогли пока", SocialAct.THANKS),
        ("пока", SocialAct.GOODBYE),
        ("до свидания", SocialAct.GOODBYE),
        ("ага", SocialAct.ACK),
        ("понятно", SocialAct.ACK),
        ("как дела?", SocialAct.HOW_ARE_YOU),
        ("ты робот?", SocialAct.IDENTITY),
        ("кто вы", SocialAct.IDENTITY),
        ("ээ", SocialAct.FILLER),
    ],
)
def test_social_turns(text: str, act: SocialAct) -> None:
    routed = route_turn(text)
    assert routed.kind is TurnKind.SOCIAL
    assert act in routed.acts
    assert routed.query == ""


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("привет! а во сколько вы работаете?", "а во сколько вы работаете?"),
        ("добрый день, подскажите как проверить баланс", "подскажите как проверить баланс"),
        ("спасибо, а сколько стоит лицензия?", "а сколько стоит лицензия?"),
        ("скажите график работы, спасибо", "скажите график работы"),
    ],
)
def test_mixed_turn_keeps_content_part(text: str, query: str) -> None:
    routed = route_turn(text)
    assert routed.kind is TurnKind.MIXED
    assert routed.query == query
    assert routed.original == text


@pytest.mark.parametrize(
    "text",
    [
        "пока не работает интернет",
        "как вы работаете в субботу",
        "что вы предлагаете по роумингу",
        "хорошо ли работает связь в турции",
        "сколько стоит лицензия",
    ],
)
def test_content_turns_not_mistaken_for_social(text: str) -> None:
    routed = route_turn(text)
    assert routed.kind is TurnKind.CONTENT
    assert routed.query == text


def test_entities_numbers_negations_survive_routing() -> None:
    routed = route_turn("здравствуйте, роуминг в египте не дороже 3 рублей?")
    assert routed.kind is TurnKind.MIXED
    for fragment in ("египте", "не", "3", "рублей"):
        assert fragment in routed.query


def test_follow_up_requires_history() -> None:
    assert route_turn("а в субботу?").kind is TurnKind.CONTENT
    assert route_turn("а в субботу?", has_history=True).kind is TurnKind.FOLLOW_UP
    assert route_turn("а сколько это стоит", has_history=True).kind is TurnKind.FOLLOW_UP


@pytest.mark.parametrize("text", ["нет", "нет, спасибо", "не надо"])
def test_decline_is_social_even_after_a_question(text: str) -> None:
    routed = route_turn(text, last_assistant_asked=True, has_history=True)
    assert routed.kind is TurnKind.SOCIAL
    assert routed.query == ""


@pytest.mark.parametrize("text", ["вы робот или человек", "ты живой человек?"])
def test_identity_questions_with_alternatives(text: str) -> None:
    routed = route_turn(text)
    assert routed.kind is TurnKind.SOCIAL
    assert SocialAct.IDENTITY in routed.acts


def test_correction_is_social_but_keeps_following_content() -> None:
    routed = route_turn("это не то", has_history=True)
    assert routed.kind is TurnKind.SOCIAL
    assert SocialAct.CORRECTION in routed.acts
    assert route_turn("не так давно подключил тариф").query == "не так давно подключил тариф"


def test_correction_lead_is_follow_up_when_history() -> None:
    routed = route_turn("нет, я имел в виду график работы", has_history=True)
    assert routed.kind is TurnKind.FOLLOW_UP
    assert SocialAct.CORRECTION in routed.acts
    assert "график работы" in routed.query
    without_history = route_turn("нет, я имел в виду график работы")
    assert without_history.kind is TurnKind.MIXED
    assert "график работы" in without_history.query


def test_contentless_turn_continues_topic_only_with_history() -> None:
    assert route_turn("сколько?", has_history=True).kind is TurnKind.FOLLOW_UP
    assert route_turn("сколько?").kind is TurnKind.SOCIAL
    assert route_turn("ээ", has_history=True).kind is TurnKind.SOCIAL
    assert route_turn("ну", has_history=True).kind is TurnKind.SOCIAL


def test_bare_yes_is_follow_up_only_after_a_question() -> None:
    assert route_turn("да", last_assistant_asked=True, has_history=True).kind is TurnKind.FOLLOW_UP
    assert route_turn("да", has_history=True).kind is TurnKind.SOCIAL


def test_stt_style_input_without_punctuation() -> None:
    routed = route_turn("ну здравствуйте ээ скажите как баланс проверить")
    assert routed.kind in (TurnKind.MIXED, TurnKind.CONTENT)
    assert "баланс" in routed.query


def test_social_replies_do_not_repeat_and_do_not_claim_humanity() -> None:
    routed = route_turn("здравствуйте")
    first = social_reply(routed)
    second = social_reply(routed, recent_answers=(first,))
    assert first != second
    assert "Куби" in first
    identity = social_reply(route_turn("ты человек?"))
    assert "Куби" in identity
    assert "не человек" in identity or "ассистент" in identity


def test_goodbye_has_no_follow_up_question() -> None:
    for text in ("пока", "до свидания", "спасибо, до свидания"):
        assert not social_reply(route_turn(text)).rstrip().endswith("?")


def test_informal_greeting_mirrors_register() -> None:
    assert social_reply(route_turn("привет")).startswith("Привет")
    assert social_prefix(route_turn("привет, сколько стоит лицензия")) == "Привет!"
    assert social_prefix(route_turn("сколько стоит лицензия")) == ""


def test_routing_is_fast() -> None:
    started = time.perf_counter()
    for _ in range(200):
        route_turn("здравствуйте, подскажите пожалуйста сколько стоит роуминг в турции")
    per_call_ms = (time.perf_counter() - started) * 1000 / 200
    assert per_call_ms < 5
