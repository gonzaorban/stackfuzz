"""Tests de la resolución tecnología -> wordlist y de su fusión."""

from pathlib import Path

from stackfuzz.detector import Tech
from stackfuzz.resolver import (
    TECH_TO_LISTS,
    build_merged_wordlist,
    count_entries,
    resolve_wordlists,
    wordlist_dir,
)


def test_every_tech_maps_to_an_existing_file():
    directory = wordlist_dir()
    for tech, names in TECH_TO_LISTS.items():
        for name in names:
            assert (directory / name).is_file(), f"{tech}: missing {name}"


def test_generic_wordlist_exists():
    assert (wordlist_dir() / "generic.txt").is_file()


def test_empty_techs_fall_back_to_generic():
    paths = resolve_wordlists(set())
    assert len(paths) == 1
    assert paths[0].name == "generic.txt"


def test_single_tech_resolves_to_its_list():
    paths = resolve_wordlists({Tech.LARAVEL})
    assert [p.name for p in paths] == ["laravel.txt"]


def test_resolution_is_deterministic_and_ordered():
    a = resolve_wordlists({Tech.EXPRESS, Tech.DJANGO})
    b = resolve_wordlists({Tech.DJANGO, Tech.EXPRESS})
    assert [p.name for p in a] == [p.name for p in b] == ["django.txt", "express.txt"]


def test_single_path_is_returned_untouched():
    only = wordlist_dir() / "generic.txt"
    assert build_merged_wordlist([only]) == only


def test_merge_dedupes_preserving_order(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("admin\napi/\nlogin\n", encoding="utf-8")
    b.write_text("api/\ndashboard\nlogin\n", encoding="utf-8")

    merged = build_merged_wordlist([a, b])
    lines = Path(merged).read_text(encoding="utf-8").splitlines()

    assert lines == ["admin", "api/", "login", "dashboard"]
    assert len(lines) == len(set(lines))


def test_merge_skips_blank_and_comment_lines(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("# comment\n\nadmin\n", encoding="utf-8")
    b.write_text("  \n# another\napi/\n", encoding="utf-8")

    merged = build_merged_wordlist([a, b])
    lines = Path(merged).read_text(encoding="utf-8").splitlines()

    assert lines == ["admin", "api/"]


# --- count_entries ------------------------------------------------------


def test_count_entries_ignores_blanks_and_comments(tmp_path: Path):
    wl = tmp_path / "wl.txt"
    wl.write_text("# comentario\n\nadmin\napi/\n   \n", encoding="utf-8")
    assert count_entries(wl) == 2


def test_count_entries_matches_bundled_list():
    generic = wordlist_dir() / "generic.txt"
    lines = [
        line.strip()
        for line in generic.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert count_entries(generic) == len(lines)


def test_count_entries_returns_zero_for_missing_file(tmp_path: Path):
    assert count_entries(tmp_path / "no-existe.txt") == 0


def test_count_entries_of_merged_list_is_deduplicated(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("admin\napi/\n", encoding="utf-8")
    b.write_text("api/\ndashboard\n", encoding="utf-8")
    merged = build_merged_wordlist([a, b])
    assert count_entries(merged) == 3
