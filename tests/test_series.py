from comicdesk.series import (
    DATE, MIXED, SEQUENTIAL, Series, build, detect_scheme, find_gaps,
    format_ranges, is_date_number, month_index, month_label, parse_ranges,
)


# --- Nummernschemata --------------------------------------------------------
def test_is_date_number_recognizes_yyyymm():
    assert is_date_number(198303) is True
    assert is_date_number(202512) is True


def test_is_date_number_rejects_plain_issue_numbers():
    assert is_date_number(42) is False
    assert is_date_number(1999) is False  # sieht wie ein Jahr aus, hat aber keinen Monat


def test_month_index_and_label_roundtrip():
    index = month_index(198303)
    assert month_label(index) == "198303"


def test_month_index_is_monotonic_across_year_boundary():
    assert month_index(198312) < month_index(198401)


def test_detect_scheme_sequential():
    assert detect_scheme([1, 2, 3, 4, 5]) == SEQUENTIAL


def test_detect_scheme_date_based():
    assert detect_scheme([198301, 198302, 198303, 198304, 198305]) == DATE


def test_detect_scheme_mixed_when_inconsistent():
    assert detect_scheme([1, 198301, 55, 3000, 9999]) == MIXED


def test_detect_scheme_empty_is_mixed():
    assert detect_scheme([]) == MIXED


# --- Luecken -----------------------------------------------------------------
def test_find_gaps_sequential():
    assert find_gaps([1, 2, 4, 5], SEQUENTIAL) == ["3"]


def test_find_gaps_none_when_complete():
    assert find_gaps([1, 2, 3], SEQUENTIAL) == []


def test_find_gaps_date_scheme():
    gaps = find_gaps([198301, 198302, 198304], DATE)
    assert gaps == ["198303"]


def test_find_gaps_mixed_scheme_reports_nothing():
    # Bei uneinheitlicher Nummerierung lieber keine Aussage als eine falsche.
    assert find_gaps([1, 198301, 3000], MIXED) == []


def test_find_gaps_needs_at_least_two_numbers():
    assert find_gaps([5], SEQUENTIAL) == []


# --- Bereichsschreibweise -----------------------------------------------------
def test_parse_ranges_expands_dash_ranges():
    assert parse_ranges("1-3, 12-14") == ["1", "2", "3", "12", "13", "14"]


def test_parse_ranges_keeps_special_issues_unchanged():
    assert parse_ranges("1, 5a, 0") == ["0", "1", "5a"]


def test_parse_ranges_deduplicates():
    assert parse_ranges("1,1,2") == ["1", "2"]


def test_parse_ranges_rejects_absurd_ranges():
    # Tippfehler wie "1-99999" soll nicht hunderttausende Eintraege erzeugen.
    assert parse_ranges("1-99999") == []


def test_parse_ranges_swaps_reversed_bounds():
    assert parse_ranges("5-3") == ["3", "4", "5"]


def test_format_ranges_collapses_consecutive_numbers():
    assert format_ranges(["1", "2", "3", "12"]) == "1-3, 12"


def test_format_ranges_roundtrips_with_parse_ranges():
    # parse_ranges sortiert numerisch, format_ranges haengt Nicht-Numerisches
    # ("5a") ans Ende an statt es einzusortieren.
    original = "1-3, 12-14, 5a"
    assert format_ranges(parse_ranges(original)) == "1-3, 12-14, 5a"


# --- Series-Eigenschaften -----------------------------------------------------
def test_series_span_sequential():
    s = Series(name="Zorro", publisher="Ehapa", numbers=[1, 2, 5])
    assert s.span == "#1–#5"


def test_series_span_date():
    s = Series(name="Zack", publisher="Ehapa", numbers=[198301, 198305],
              scheme=DATE)
    assert s.span == "198301–198305"


def test_series_span_empty():
    s = Series(name="Empty", publisher=None)
    assert s.span == "–"


def test_series_effective_gaps_uses_manual_reference_when_set():
    s = Series(name="Zorro", publisher=None, numbers=[1, 2, 3],
              gaps=["4"], manual_numbers=["1", "2", "3", "4", "5"])
    assert s.effective_gaps == ["4", "5"]


def test_series_effective_gaps_falls_back_to_detected_gaps():
    s = Series(name="Zorro", publisher=None, numbers=[1, 2, 4], gaps=["3"])
    assert s.effective_gaps == ["3"]


def test_series_unexpected_numbers_not_in_reference():
    s = Series(name="Zorro", publisher=None, numbers=[1, 2, 99],
              manual_numbers=["1", "2", "3"])
    assert s.unexpected == ["99"]


def test_series_missing_after_highest_owned_issue():
    s = Series(name="Zorro", publisher=None, numbers=[1, 2, 3],
              known_numbers=["1", "2", "3", "4", "5"])
    assert s.missing_after == ["4", "5"]


def test_series_missing_known_ignores_order_of_reference():
    s = Series(name="Zorro", publisher=None, numbers=[2],
              known_numbers=["1", "2", "3"])
    assert s.missing_known == ["1", "3"]


def test_series_probe_ids_spreads_across_range():
    samples = [(float(n), f"id{n}") for n in range(1, 11)]
    s = Series(name="Zorro", publisher=None, samples=samples)
    ids = s.probe_ids(count=4)
    assert len(ids) == 4
    assert ids[0] == "id1"
    assert ids[-1] == "id10"


def test_series_probe_ids_empty_without_samples():
    s = Series(name="Zorro", publisher=None)
    assert s.probe_ids() == []


# --- build() -------------------------------------------------------------
def test_build_groups_rows_by_series_and_publisher():
    rows = [
        {"series": "Zorro", "publisher": "Ehapa", "path": "/a/1.cbz",
         "issue_sort": 1.0, "source": "comicvine", "source_id": "1"},
        {"series": "Zorro", "publisher": "Ehapa", "path": "/a/2.cbz",
         "issue_sort": 2.0, "source": "comicvine", "source_id": "2"},
        {"series": "Zack", "publisher": "Ehapa", "path": "/b/1.cbz",
         "issue_sort": 1.0, "source": None, "source_id": None},
    ]
    series = build(rows)
    names = [s.name for s in series]
    assert names == ["Zack", "Zorro"]  # alphabetisch, case-insensitiv
    zorro = next(s for s in series if s.name == "Zorro")
    assert zorro.count == 2
    assert zorro.scheme == SEQUENTIAL
    assert zorro.source == "comicvine"


def test_build_skips_rows_without_series_name():
    rows = [{"series": "  ", "publisher": None, "path": "/a.cbz",
             "issue_sort": 1.0, "source": None, "source_id": None}]
    assert build(rows) == []
