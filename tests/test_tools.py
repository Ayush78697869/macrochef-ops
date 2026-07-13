"""Unit tests - pure logic + SQL against a tiny fixture DB. No LLM calls (CI-safe)."""
import sqlite3

import pytest

from src import tools

MEALS = [
    # id, meal_id, name, meal_type, calories, protein_g, carbs_g, fat_g,
    # prep_minutes, ingredients, rating
    ("recME00001", "M-DI000", "grilled chicken bowl", "dinner",
     520, 45, 40, 18, 25, "chicken, brown rice, olive oil", 4.8),
    ("recME00002", "M-DI001", "paneer tikka plate", "dinner",
     610, 32, 55, 24, 30, "paneer, spices, cream", 4.5),
    ("recME00003", "M-BR000", "oats banana smoothie", "breakfast",
     320, 14, 55, 6, 5, "oats, banana, greek yogurt", 4.2),
    ("recME00004", "M-DI002", "tofu stir fry", "dinner",
     380, 28, 30, 16, 20, "tofu, broccoli, sesame oil", 4.6),
    ("recME00005", "M-SN000", "peanut butter bar", "snack",
     250, 8, 20, 15, 5, "peanut butter, oats, honey", 4.9),
]
CLIENTS = [
    ("recCL00001", "CL-1000", "Test Person", "test@example.com", "vegetarian",
     "dairy", 1800.0, 100.0, 1),
    ("recCL00002", "CL-1001", "Nut Free", "nf@example.com", "none",
     "peanut, tree nut", 2200.0, 140.0, 1),
]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE meals (id TEXT PRIMARY KEY, meal_id TEXT,
        name TEXT, meal_type TEXT, calories REAL, protein_g REAL, carbs_g REAL,
        fat_g REAL, prep_minutes INTEGER, ingredients TEXT, rating REAL)""")
    con.execute("""CREATE TABLE clients (id TEXT PRIMARY KEY, client_id TEXT,
        name TEXT, email TEXT, diet TEXT, allergies TEXT,
        calorie_target REAL, protein_target_g REAL, active INTEGER)""")
    con.executemany("INSERT INTO meals VALUES (" + ",".join("?" * 11) + ")", MEALS)
    con.executemany("INSERT INTO clients VALUES (" + ",".join("?" * 9) + ")", CLIENTS)
    con.commit()
    con.close()
    monkeypatch.setattr(tools, "DB_PATH", str(path))


def test_get_client_profile_by_id_and_name(db):
    assert tools.get_client_profile("CL-1001")["name"] == "Nut Free"
    assert tools.get_client_profile("Test")["client_id"] == "CL-1000"
    assert "error" in tools.get_client_profile("Nobody McFake")


def test_search_filters_and_sort(db):
    res = tools.search_meals(meal_type="dinner", min_protein_g=30,
                             sort_by="protein_desc")
    assert [r["id"] for r in res] == ["recME00001", "recME00002"]


def test_search_excludes_ingredients(db):
    res = tools.search_meals(meal_type="dinner", exclude_ingredients=["soy"])
    assert "recME00004" not in [r["id"] for r in res]  # tofu is soy


def test_allergen_expansion_catches_derived_ingredients(db):
    # 'dairy' must flag paneer/cream even though the word 'dairy' appears nowhere
    v = tools.find_allergen_violations(["recME00002"], ["dairy"])
    assert v and v[0]["allergens_found"] == ["dairy"]
    # and the smoothie's greek yogurt too
    assert tools.find_allergen_violations(["recME00003"], ["dairy"])


def test_plan_check_passes_within_tolerance(db):
    res = tools.check_plan_against_targets(
        ["recME00001", "recME00003", "recME00004"],
        {"calories": 1250, "protein_g": 90})
    assert res["pass"] is True
    assert res["detail"]["calories"]["actual"] == 1220.0


def test_plan_check_fails_outside_tolerance(db):
    res = tools.check_plan_against_targets(["recME00003"], {"protein_g": 150})
    assert res["pass"] is False


def test_plan_check_fails_on_allergen(db):
    res = tools.check_plan_against_targets(
        ["recME00005"], {"calories": 250}, allergies=["peanut"])
    assert res["pass"] is False
    assert res["allergen_violations"][0]["allergens_found"] == ["peanut"]


def test_plan_check_flags_missing_ids(db):
    res = tools.check_plan_against_targets(["recME00001", "recNOPE"],
                                           {"calories": 520})
    assert res["missing_ids"] == ["recNOPE"]
    assert res["pass"] is False