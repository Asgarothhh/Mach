from mts_rag.query import query_variants


def test_variant_drops_fillers() -> None:
    variants = query_variants("алло подскажите график работы", max_query_variants=3)
    assert variants[0] == "алло подскажите график работы"
    assert variants[1] == "график работы"


def test_variant_skipped_when_empty_or_equal() -> None:
    assert query_variants("алло", max_query_variants=3) == ("алло",)
    assert query_variants("график работы", max_query_variants=3) == ("график работы",)


def test_protected_negations_and_digits_kept() -> None:
    assert query_variants("нет roaming 100", max_query_variants=3) == ("нет roaming 100",)
    assert query_variants("без roaming", max_query_variants=3) == ("без roaming",)


def test_capped_by_max_query_variants() -> None:
    assert query_variants("ну график работы", max_query_variants=1) == ("ну график работы",)
