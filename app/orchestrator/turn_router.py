"""Deterministic turn router: social / mixed / content / follow_up (SSOT routing budget 5–25 ms).

Rules only, no model call. The retrieval query is the user text with leading/trailing
social phrases removed; entities, numbers and negations are never touched, and the
original text is always kept for the LLM prompt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from mts_rag.lexical import query_terms


class TurnKind(StrEnum):
    SOCIAL = "social"
    MIXED = "mixed"
    CONTENT = "content"
    FOLLOW_UP = "follow_up"


class SocialAct(StrEnum):
    GREETING = "greeting"
    THANKS = "thanks"
    GOODBYE = "goodbye"
    ACK = "ack"
    HOW_ARE_YOU = "how_are_you"
    IDENTITY = "identity"
    DECLINE = "decline"
    CORRECTION = "correction"
    FILLER = "filler"


@dataclass(frozen=True)
class RoutedTurn:
    kind: TurnKind
    acts: tuple[SocialAct, ...]
    original: str
    query: str
    informal: bool = False


_PUNCT = r"[\s,.!?;:…\-—]"
_SEP = rf"{_PUNCT}*"

# Whole-phrase patterns; order matters (longer phrases first).
_PHRASES: tuple[tuple[SocialAct, str], ...] = (
    (
        SocialAct.GREETING,
        r"добр(?:ый|ого)\s+(?:день|дня|вечер|вечера)|доброе\s+утро|доброго\s+времени\s+суток",
    ),
    (
        SocialAct.GREETING,
        r"здравствуй(?:те)?|приветствую|привет(?:ик)?|хай|алло|ал[её]|hello|hi",
    ),
    (
        SocialAct.THANKS,
        r"(?:большое|огромное)\s+спасибо"
        r"|спасибо(?:\s+(?:большое|огромное|вам|за\s+помощь|за\s+информацию))*"
        r"|благодарю(?:\s+вас)?|спс"
        r"|(?:вы|ты)\s+(?:мне\s+)?(?:очень\s+)?(?:помогли|помогла|помог|выручили|выручил[аи]?)",
    ),
    (
        SocialAct.GOODBYE,
        r"до\s+свидания|всего\s+(?:доброго|хорошего)|до\s+встречи|хорошего\s+дня|пока(?:-пока)?",
    ),
    (
        SocialAct.HOW_ARE_YOU,
        r"как\s+(?:у\s+(?:вас|тебя)\s+)?дела|как\s+(?:ты|вы)\s+поживаете|как\s+поживаешь"
        r"|как\s+(?:ты|вы)(?=[\s?!.]*$)",
    ),
    (
        SocialAct.IDENTITY,
        r"кто\s+(?:ты|вы)(?:\s+такой|\s+такая|\s+такие)?(?=[\s?!.]*$)|что\s+(?:ты|вы)\s+такое"
        r"|(?:ты|вы)\s+(?:робот|бот|живой\s+человек|человек)"
        r"(?:\s+или\s+(?:робот|бот|живой\s+человек|человек))?"
        r"|я\s+говорю\s+с\s+(?:роботом|ботом|человеком)",
    ),
    (
        SocialAct.CORRECTION,
        r"(?:это\s+)?не\s+(?:то|так|об\s+этом|про\s+это)"
        r"|(?:вы|ты)\s+(?:меня\s+)?не\s+(?:так\s+)?понял[аи]?",
    ),
    (
        SocialAct.ACK,
        r"(?:(?:вс[её]|теперь)\s+)?(?:понятно|ясно|хорошо|отлично|супер)"
        r"|ладно|окей|ок|ok|угу|ага|договорились|принято",
    ),
)
_TAIL_ACTS = frozenset({SocialAct.THANKS, SocialAct.GOODBYE, SocialAct.GREETING})
_SOCIAL_PATTERNS: tuple[tuple[SocialAct, re.Pattern[str], re.Pattern[str]], ...] = tuple(
    (
        act,
        re.compile(rf"^{_SEP}(?:{phrase})(?=$|{_PUNCT}){_SEP}", re.IGNORECASE),
        re.compile(rf"(?:^|{_PUNCT}){_SEP}(?:{phrase}){_SEP}$", re.IGNORECASE),
    )
    for act, phrase in _PHRASES
)
# Short replies that only make sense as an answer to the assistant's last question.
_AFFIRM = re.compile(r"^(?:да|конечно|давайте|давай|можно|да\s+давайте)$", re.IGNORECASE)
_DECLINE = re.compile(r"^(?:нет|не\s+надо|не\s+нужно|нет\s+не\s+надо)$", re.IGNORECASE)
# Leading phrases kept when real content follows ("пока не работает", "не так давно ...").
_LEAD_ONLY_WHEN_ALONE = frozenset({SocialAct.GOODBYE, SocialAct.ACK, SocialAct.CORRECTION})
_FILLER = re.compile(r"^(?:э+|м+|а+|ну|так|слушайте|слушай)$", re.IGNORECASE)
_ELLIPSIS_START = re.compile(r"^(?:а|и)\b", re.IGNORECASE)
_ANAPHORA = re.compile(
    r"\b(?:это|этого|этом|этой|эту|там|туда|тут|его|её|ее|их|тот|та|те|такой|такая|такое)\b",
    re.IGNORECASE,
)
_INFORMAL = re.compile(r"\b(?:привет|хай|пока|ты|тебя|тебе|спс|ок)\b", re.IGNORECASE)
_MAX_ELLIPTIC_TERMS = 3


def _normalize(text: str) -> str:
    cleaned = unicodedata.normalize("NFC", text)
    return " ".join(cleaned.split())


def _strip_social(text: str) -> tuple[str, list[SocialAct]]:
    """Remove social phrases at the start and end of the text, collecting their acts."""
    acts: list[SocialAct] = []
    remainder = text
    changed = True
    while changed and remainder:
        changed = False
        for act, lead_pattern, tail_pattern in _SOCIAL_PATTERNS:
            lead = lead_pattern.match(remainder)
            # "пока не работает" / "хорошо ли ..." are not goodbyes or acknowledgements.
            if lead and act in _LEAD_ONLY_WHEN_ALONE and query_terms(remainder[lead.end() :]):
                lead = None
            if lead:
                acts.append(act)
                remainder = remainder[lead.end() :]
                changed = True
                break
            tail = tail_pattern.search(remainder) if act in _TAIL_ACTS else None
            if tail:
                acts.append(act)
                remainder = remainder[: tail.start()]
                changed = True
                break
    return remainder.strip(" ,.;:—-"), acts


def route_turn(
    text: str, *, last_assistant_asked: bool = False, has_history: bool = False
) -> RoutedTurn:
    original = _normalize(text)
    remainder, acts = _strip_social(original)
    informal = bool(_INFORMAL.search(original))
    unique_acts = tuple(dict.fromkeys(acts))

    if not remainder:
        if not unique_acts:
            unique_acts = (SocialAct.FILLER,)
        return RoutedTurn(TurnKind.SOCIAL, unique_acts, original, "", informal)

    bare = " ".join(remainder.strip(" ?!.,").casefold().replace(",", " ").split())
    if _DECLINE.match(bare):
        return RoutedTurn(
            TurnKind.SOCIAL, unique_acts or (SocialAct.DECLINE,), original, "", informal
        )
    if _AFFIRM.match(bare):
        if last_assistant_asked:
            return RoutedTurn(TurnKind.FOLLOW_UP, unique_acts, original, remainder, informal)
        return RoutedTurn(
            TurnKind.SOCIAL, unique_acts or (SocialAct.ACK,), original, "", informal
        )

    if all(_FILLER.match(word) for word in bare.split()):
        return RoutedTurn(
            TurnKind.SOCIAL, unique_acts or (SocialAct.FILLER,), original, "", informal
        )

    terms = query_terms(remainder)
    elliptic = len(terms) <= _MAX_ELLIPTIC_TERMS and bool(
        _ELLIPSIS_START.match(remainder) or _ANAPHORA.search(remainder)
    )
    if has_history and (not terms or elliptic):
        return RoutedTurn(TurnKind.FOLLOW_UP, unique_acts, original, remainder, informal)

    if not terms:
        return RoutedTurn(
            TurnKind.SOCIAL, unique_acts or (SocialAct.FILLER,), original, "", informal
        )

    kind = TurnKind.MIXED if unique_acts else TurnKind.CONTENT
    return RoutedTurn(kind, unique_acts, original, remainder, informal)


_REPLIES: dict[SocialAct, tuple[str, ...]] = {
    SocialAct.GREETING: (
        "Здравствуйте! Чем могу помочь?",
        "Добрый день! Слушаю вас.",
        "Здравствуйте! Подскажите, какой у вас вопрос?",
    ),
    SocialAct.THANKS: (
        "Пожалуйста! Если появятся ещё вопросы — обращайтесь.",
        "Всегда пожалуйста.",
        "Пожалуйста! Могу ещё чем-то помочь?",
    ),
    SocialAct.GOODBYE: (
        "Всего доброго!",
        "До свидания, хорошего дня!",
    ),
    SocialAct.ACK: (
        "Хорошо. Если будут вопросы — я на связи.",
        "Отлично. Что-нибудь ещё подсказать?",
        "Принято. Обращайтесь, если что-то понадобится.",
    ),
    SocialAct.HOW_ARE_YOU: (
        "Спасибо, всё работает исправно. Чем могу помочь?",
        "Спасибо, что спросили! Чем могу помочь?",
    ),
    SocialAct.IDENTITY: (
        "Я виртуальный голосовой помощник, не человек. Отвечаю на вопросы по услугам компании.",
        "Я голосовой ассистент компании. Подскажу по услугам, ценам и графику работы, "
        "если это есть в базе знаний.",
    ),
    SocialAct.DECLINE: (
        "Хорошо. Если понадобится что-то ещё — обращайтесь.",
        "Договорились. Обращайтесь, если будут вопросы.",
    ),
    SocialAct.CORRECTION: (
        "Извините. Уточните, пожалуйста, что именно вас интересует?",
        "Простите за неточность. Скажите, о чём именно рассказать?",
    ),
    SocialAct.FILLER: (
        "Слушаю вас.",
        "Да, слушаю. Какой у вас вопрос?",
    ),
}
_INFORMAL_GREETINGS = ("Привет! Чем могу помочь?", "Привет! Слушаю.")
_PRIMARY_ORDER = (
    SocialAct.GOODBYE,
    SocialAct.THANKS,
    SocialAct.CORRECTION,
    SocialAct.IDENTITY,
    SocialAct.HOW_ARE_YOU,
    SocialAct.GREETING,
    SocialAct.DECLINE,
    SocialAct.ACK,
    SocialAct.FILLER,
)


def _pick(options: tuple[str, ...], recent: tuple[str, ...]) -> str:
    for option in options:
        if option not in recent:
            return option
    return options[0]


def social_reply(routed: RoutedTurn, *, recent_answers: tuple[str, ...] = ()) -> str:
    """Short reply for a purely social turn; avoids repeating recent assistant phrases."""
    acts = set(routed.acts) or {SocialAct.FILLER}
    primary = next(act for act in _PRIMARY_ORDER if act in acts)
    if primary is SocialAct.GREETING and routed.informal:
        return _pick(_INFORMAL_GREETINGS, recent_answers)
    reply = _pick(_REPLIES[primary], recent_answers)
    if primary is SocialAct.GOODBYE and SocialAct.THANKS in acts:
        return f"Пожалуйста! {reply}"
    if primary in (SocialAct.IDENTITY, SocialAct.HOW_ARE_YOU) and SocialAct.GREETING in acts:
        return f"{'Привет!' if routed.informal else 'Здравствуйте!'} {reply}"
    return reply


def social_prefix(routed: RoutedTurn) -> str:
    """Greeting prefix for a deterministic (non-LLM) answer to a mixed turn."""
    if SocialAct.GREETING not in routed.acts:
        return ""
    return "Привет!" if routed.informal else "Здравствуйте!"
