"""Lexical matching used by the stub retriever and the Qdrant relevance gate.

``tokenize`` is the raw surface tokenizer. ``query_terms`` / ``document_terms`` build the
normalized term sets the relevance gate compares: a light Snowball-style Russian stemmer,
a small set of service-desk synonym concepts, and (query side only) removal of function
words, question words and politeness fillers so they do not dilute term coverage.
Negation particles are excluded from coverage but never removed from query text.
"""

import re
import unicodedata
from collections.abc import Iterable, Set

_TOKEN = re.compile(r"\w+")

NEGATIONS = frozenset({"не", "нет", "без", "ни"})

# Words that carry no retrievable meaning in a support question. Entities, numbers,
# dates, places and negations are never listed here.
# fmt: off
_QUERY_STOPWORDS = frozenset(
    {
        # politeness, fillers, discourse markers
        "ну", "вот", "пожалуйста", "скажите", "подскажите", "расскажите", "уточните",
        "скажи", "подскажи", "расскажи", "уточни",
        "здравствуйте", "здравствуй", "привет", "алло", "добрый", "доброе", "доброго",
        "спасибо", "благодарю", "ээ", "эээ", "мм", "ммм", "короче", "слушайте", "слушай",
        "извините", "простите", "кстати", "вообще", "просто", "типа", "ладно", "хорошо",
        "можно", "могу", "можете", "могли", "бы", "хочу", "хотел", "хотела", "хотелось",
        "интересует", "интересно", "узнать", "знать", "нужно", "надо", "нужна", "нужен",
        "подсказать", "сказать", "понятно", "ясно", "отлично", "супер", "ок", "окей", "ага",
        "угу", "все", "всё", "теперь", "сейчас", "пока",
        # question words
        "как", "какой", "какая", "какое", "какие", "каких", "каким", "какую", "каков",
        "какого", "каком", "какому", "какими", "только", "лишь",
        "сколько", "скольки", "когда", "где", "куда", "откуда", "что", "чем", "чего",
        "почему", "зачем", "кто", "кого", "ли", "разве",
        # pronouns
        "я", "мне", "меня", "мной", "мы", "нам", "нас", "вы", "вам", "вас", "вами", "ты",
        "тебе", "тебя", "он", "она", "оно", "они", "его", "ее", "её", "их", "им", "это",
        "этот", "эта", "эти", "этого", "этой", "этом", "тот", "та", "то", "там", "тут",
        "мой", "моя", "мои", "мое", "моё", "ваш", "ваша", "ваше", "ваши", "вашей", "вашего",
        "свой", "свою", "своей",
        # prepositions, conjunctions, particles
        "а", "и", "или", "но", "да", "же", "в", "во", "на", "с", "со", "к", "ко", "у",
        "о", "об", "обо", "от", "до", "по", "за", "из", "для", "при", "про", "под",
        "над", "через", "чтобы", "если", "так", "уже", "еще", "ещё", "есть",
        "был", "была", "было", "будет", "быть",
    }
)

# Surface forms mapped to one concept id so paraphrases of the same support need match.
# Only generic service-desk concepts; tenant entities are never merged here.
_CONCEPTS: dict[str, tuple[str, ...]] = {
    "#price": (
        "цена", "цены", "цену", "ценой", "цене", "стоимость", "стоимости", "стоит",
        "стоят", "стоить", "почем", "почём", "прайс", "платить", "плата", "оплата",
    ),
    "#hours": (
        "график", "графику", "графика", "режим", "режиме", "расписание", "расписанию",
        "открыт", "открыта", "открыто", "открыты", "открывается", "открываетесь",
        "открываются", "работает", "работаете", "работают",
    ),
    "#contact": (
        # "связь" / "оператор" mean network / carrier in telecom, so they are not merged.
        "контакты", "контакт", "контактов", "связаться", "написать",
        "писать", "почта", "почту", "почты", "email", "mail", "имейл", "емейл",
        "мейл", "электронка", "электронную",
    ),
    "#support": (
        "поддержка", "поддержку", "поддержки", "поддержкой", "техподдержка",
        "техподдержку", "техподдержки", "саппорт",
    ),
    "#balance": (
        "баланс", "баланса", "балансе", "счет", "счёт", "счете", "счёте", "счету", "счёту",
    ),
}
# fmt: on
_SURFACE_CONCEPT = {
    surface: concept for concept, surfaces in _CONCEPTS.items() for surface in surfaces
}

_MIN_PREFIX = 4
# A shared prefix bridges inflections ("открыт" / "открыты"), not new words ("банк" / "банкомат").
_MAX_PREFIX_GAP = 2

_VOWELS = frozenset("аеиоуыэюя")
# fmt: off
_PERFECTIVE_GERUND_1 = ("вшись", "вши", "в")
_PERFECTIVE_GERUND_2 = ("ившись", "ывшись", "ивши", "ывши", "ив", "ыв")
_ADJECTIVE = (
    "ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие", "ые", "ое", "ей", "ий", "ый",
    "ой", "ем", "им", "ым", "ом", "их", "ых", "ую", "юю", "ая", "яя", "ою", "ею",
)
_PARTICIPLE_1 = ("ем", "нн", "вш", "ющ", "щ")
_PARTICIPLE_2 = ("ивш", "ывш", "ующ")
_REFLEXIVE = ("ся", "сь")
_VERB_1 = (
    "ете", "йте", "ешь", "нно", "ла", "на", "ли", "ем", "ло", "но", "ет", "ют", "ны",
    "ть", "й", "л", "н",
)
_VERB_2 = (
    "ейте", "уйте", "ила", "ыла", "ена", "ите", "или", "ыли", "ило", "ыло", "ено", "ует",
    "уют", "ены", "ить", "ыть", "ишь", "ей", "уй", "ил", "ыл", "им", "ым", "ен", "ят",
    "ит", "ыт", "ую", "ю",
)
_NOUN = (
    "иями", "ями", "ами", "ией", "иям", "ием", "иях", "ев", "ов", "ие", "ье", "еи", "ии",
    "ей", "ой", "ий", "ям", "ем", "ам", "ом", "ах", "ях", "ию", "ью", "ия", "ья", "а",
    "е", "и", "й", "о", "у", "ы", "ь", "ю", "я",
)
# fmt: on


def tokenize(text: str) -> list[str]:
    """NFC, casefold, then split on Unicode word characters. Digits are kept; no stemming."""
    return _TOKEN.findall(unicodedata.normalize("NFC", text).casefold())


def lexical_score(query_terms: Set[str], document_terms: Set[str]) -> float:
    """Share of distinct query terms present in the document, in [0, 1]."""
    if not query_terms:
        return 0.0
    return len(query_terms & document_terms) / len(query_terms)


def _regions(word: str) -> tuple[int, int]:
    rv = len(word)
    for index, char in enumerate(word):
        if char in _VOWELS:
            rv = index + 1
            break
    r1 = len(word)
    for index in range(1, len(word)):
        if word[index] not in _VOWELS and word[index - 1] in _VOWELS:
            r1 = index + 1
            break
    r2 = len(word)
    for index in range(r1 + 1, len(word)):
        if word[index] not in _VOWELS and word[index - 1] in _VOWELS:
            r2 = index + 1
            break
    return rv, r2


def _strip(word: str, start: int, suffixes: Iterable[str], *, after_a: bool = False) -> str | None:
    for suffix in sorted(suffixes, key=len, reverse=True):
        cut = len(word) - len(suffix)
        if cut < start or not word.endswith(suffix):
            continue
        if after_a and (cut - 1 < start or word[cut - 1] not in "ая"):
            continue
        return word[:cut]
    return None


def _strip_adjectival(word: str, rv: int) -> str | None:
    stem = _strip(word, rv, _ADJECTIVE)
    if stem is None:
        return None
    participle = _strip(stem, rv, _PARTICIPLE_1, after_a=True) or _strip(stem, rv, _PARTICIPLE_2)
    return participle if participle is not None else stem


def stem(word: str) -> str:
    """Light Snowball-style Russian stemmer. Non-Cyrillic and digit tokens are unchanged."""
    word = word.replace("ё", "е")
    if not any(char in _VOWELS for char in word):
        return word
    rv, r2 = _regions(word)
    result = _strip(word, rv, _PERFECTIVE_GERUND_1, after_a=True) or _strip(
        word, rv, _PERFECTIVE_GERUND_2
    )
    if result is None:
        base = _strip(word, rv, _REFLEXIVE) or word
        result = (
            _strip_adjectival(base, rv)
            or _strip(base, rv, _VERB_1, after_a=True)
            or _strip(base, rv, _VERB_2)
            or _strip(base, rv, _NOUN)
            or base
        )
    if result.endswith("и") and len(result) - 1 >= rv:
        result = result[:-1]
    for suffix in ("ость", "ост"):
        if result.endswith(suffix) and len(result) - len(suffix) >= r2:
            result = result[: -len(suffix)]
            break
    if result.endswith("нн") and len(result) - 2 >= rv:
        return result[:-1]
    superlative = _strip(result, rv, ("ейше", "ейш"))
    if superlative is not None:
        result = superlative
        if result.endswith("нн") and len(result) - 2 >= rv:
            result = result[:-1]
    elif result.endswith("ь") and len(result) - 1 >= rv:
        result = result[:-1]
    return result or word


def normalize_term(token: str) -> str:
    concept = _SURFACE_CONCEPT.get(token.replace("ё", "е")) or _SURFACE_CONCEPT.get(token)
    if concept is not None:
        return concept
    return stem(token)


def is_stopword(token: str) -> bool:
    return token in _QUERY_STOPWORDS or token.replace("ё", "е") in _QUERY_STOPWORDS


def index_terms(text: str) -> list[str]:
    """Normalized tokens for sparse indexing and search (order and repeats kept)."""
    return [normalize_term(token) for token in tokenize(text)]


def query_terms_from_tokens(tokens: Iterable[str]) -> frozenset[str]:
    return frozenset(
        normalize_term(token)
        for token in tokens
        if not is_stopword(token) and token not in NEGATIONS
    )


def query_terms(text: str) -> frozenset[str]:
    """Normalized content terms of a query: stopwords and negation particles excluded."""
    return query_terms_from_tokens(tokenize(text))


def document_terms_from_tokens(tokens: Iterable[str]) -> frozenset[str]:
    return frozenset(normalize_term(token) for token in tokens)


def document_terms(text: str) -> frozenset[str]:
    return document_terms_from_tokens(tokenize(text))


def _matches(term: str, document: Set[str]) -> bool:
    if term in document:
        return True
    if term.startswith("#") or len(term) < _MIN_PREFIX or term.isdigit():
        return False
    return any(
        len(other) >= _MIN_PREFIX
        and not other.startswith("#")
        and abs(len(other) - len(term)) <= _MAX_PREFIX_GAP
        and (other.startswith(term) or term.startswith(other))
        for other in document
    )


def term_coverage(query: Set[str], document: Set[str]) -> float:
    """Share of query content terms found in the document (exact, concept or shared stem)."""
    if not query:
        return 0.0
    return sum(1 for term in query if _matches(term, document)) / len(query)
