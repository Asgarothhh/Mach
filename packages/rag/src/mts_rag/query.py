"""Local query variants (SSOT §6.7.3). No LLM rewrite."""

from mts_rag.lexical import tokenize

_FILLERS = frozenset(
    {
        "ну",
        "вот",
        "пожалуйста",
        "скажите",
        "подскажите",
        "здравствуйте",
        "алло",
        "ээ",
        "эээ",
        "мм",
    }
)
_PROTECTED = frozenset({"не", "нет", "без"})


def query_variants(normalized_query: str, *, max_query_variants: int) -> tuple[str, ...]:
    """v1 is the normalized query. v2 drops a conservative filler stoplist.

    v2 is omitted when it would remove не/нет/без or digits, when it equals v1, or when empty.
    """
    v1 = normalized_query
    if max_query_variants < 2:
        return (v1,)
    kept: list[str] = []
    for word in v1.split():
        tokens = tokenize(word)
        if tokens and all(tok in _FILLERS for tok in tokens):
            if any(
                tok in _PROTECTED or tok.isdigit() or any(ch.isdigit() for ch in tok)
                for tok in tokens
            ):
                return (v1,)
            continue
        kept.append(word)
    v2 = " ".join(kept)
    if not v2 or v2 == v1:
        return (v1,)
    return (v1, v2)[:max_query_variants]
