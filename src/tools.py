"""Agent tools over the ops snapshot (Airtable -> SQLite). The two validators
are DETERMINISTIC on purpose: LLMs can't do reliable arithmetic or exhaustive
screening - verifiable subtasks should be code."""
import os
import sqlite3

from src import retrieval

DB_PATH = os.getenv("MACROCHEF_DB", "data/ops.sqlite")

# Whitelist mapping -> ORDER BY is never built from model input (no injection)
SORTS = {
    "rating_desc": "rating DESC",
    "protein_desc": "protein_g DESC",
    "calories_asc": "calories ASC",
    "minutes_asc": "prep_minutes ASC",
}

# An allergy like "dairy" must catch cheddar/yogurt/paneer, "wheat" must catch
# flour/bread/noodles. Substring-matching the allergy word alone silently
# misses these - this map is the fix (found via testing; great interview story).
ALLERGEN_KEYWORDS = {
    "peanut": ["peanut"],
    "tree nut": ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut"],
    "dairy": ["milk", "cheese", "butter", "yogurt", "cream", "paneer",
              "cheddar", "mozzarella", "parmesan", "ghee"],
    "egg": ["egg"],
    "soy": ["soy", "tofu", "edamame", "tempeh"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "scallop"],
    "wheat": ["wheat", "flour", "bread", "pasta", "noodle", "tortilla", "cracker"],
    "sesame": ["sesame", "tahini"],
}


def expand_allergens(allergies):
    """['dairy', 'peanut'] -> every keyword the ingredient text must not contain."""
    words = []
    for a in allergies or []:
        a = a.strip().lower()
        if a:
            words.extend(ALLERGEN_KEYWORDS.get(a, [a]))
    return words


def _connect():
    return sqlite3.connect(DB_PATH)


def get_client_profile(name_or_id):
    """Look up a client by Client ID (CL-1003), name, or email fragment."""
    like = f"%{name_or_id}%"
    with _connect() as con:
        row = con.execute(
            """SELECT client_id, name, email, diet, allergies,
                      calorie_target, protein_target_g, active
               FROM clients
               WHERE client_id = ? OR name LIKE ? OR email LIKE ? LIMIT 1""",
            (name_or_id, like, like)).fetchone()
    if not row:
        return {"error": f"no client matching '{name_or_id}'"}
    cols = ["client_id", "name", "email", "diet", "allergies",
            "calorie_target", "protein_target_g", "active"]
    return dict(zip(cols, row))


def search_meals(min_protein_g=None, max_calories=None, meal_type=None,
                 exclude_ingredients=None, max_minutes=None, name_contains=None,
                 sort_by="rating_desc", limit=5):
    """exclude_ingredients: allergen/ingredient words to filter OUT (expanded
    via ALLERGEN_KEYWORDS) - how client allergies are enforced at SQL level.
    Returns compact dicts only - full detail would blow the 8B model's context."""
    q = ("SELECT id, meal_id, name, meal_type, calories, protein_g, carbs_g, "
         "fat_g, prep_minutes FROM meals WHERE 1=1")
    params = []
    if min_protein_g is not None:
        q += " AND protein_g >= ?"; params.append(float(min_protein_g))
    if max_calories is not None:
        q += " AND calories <= ?"; params.append(float(max_calories))
    if max_minutes is not None:
        q += " AND prep_minutes <= ?"; params.append(int(max_minutes))
    if meal_type:
        q += " AND meal_type = ?"; params.append(meal_type)
    if name_contains:
        q += " AND name LIKE ?"; params.append(f"%{name_contains}%")
    for word in expand_allergens(exclude_ingredients):
        q += " AND LOWER(ingredients) NOT LIKE ? AND LOWER(name) NOT LIKE ?"
        params.extend([f"%{word}%", f"%{word}%"])
    q += f" ORDER BY {SORTS.get(sort_by, SORTS['rating_desc'])} LIMIT ?"
    params.append(min(int(limit), 20))
    with _connect() as con:
        rows = con.execute(q, params).fetchall()
    cols = ["id", "meal_id", "name", "meal_type", "calories", "protein_g",
            "carbs_g", "fat_g", "prep_minutes"]
    return [dict(zip(cols, r)) for r in rows]


def lookup_nutrition_guidance(question):
    """RAG lookup - cited excerpts for the agent to ground claims in."""
    chunks = retrieval.retrieve(question, k=4)
    return "\n\n".join(f"[{c['source']} p.{c['page']}] {c['text'][:600]}"
                       for c in chunks)


def compute_plan_macros(meal_ids):
    """DETERMINISTIC. meal_ids are snapshot record ids (strings like 'rec...')."""
    ids = [str(i) for i in meal_ids]
    marks = ",".join("?" * len(ids))
    with _connect() as con:
        rows = con.execute(
            f"SELECT id, name, calories, protein_g, carbs_g, fat_g "
            f"FROM meals WHERE id IN ({marks})", ids).fetchall()
    found = {r[0] for r in rows}
    return {
        "meals": [{"id": r[0], "name": r[1], "calories": r[2], "protein_g": r[3]}
                  for r in rows],
        "totals": {"calories": round(sum(r[2] for r in rows), 1),
                   "protein_g": round(sum(r[3] for r in rows), 1),
                   "carbs_g": round(sum(r[4] for r in rows), 1),
                   "fat_g": round(sum(r[5] for r in rows), 1)},
        "missing_ids": [i for i in ids if i not in found],
    }


def check_plan_against_targets(meal_ids, targets, allergies=None, tolerance_pct=10):
    """DETERMINISTIC: macro deviation vs targets AND allergen screening."""
    macros = compute_plan_macros(meal_ids)
    report, ok = {}, True
    for key, target in (targets or {}).items():
        actual = macros["totals"].get(key)
        if actual is None or not target:
            continue
        dev = (actual - float(target)) / float(target) * 100
        passed = abs(dev) <= tolerance_pct
        ok = ok and passed
        report[key] = {"target": target, "actual": actual,
                       "deviation_pct": round(dev, 1), "pass": passed}
    violations = find_allergen_violations(meal_ids, allergies or [])
    ok = ok and not violations and not macros["missing_ids"]
    return {"pass": ok, "detail": report,
            "allergen_violations": violations, "missing_ids": macros["missing_ids"]}


def find_allergen_violations(meal_ids, allergies):
    """Keyword screen of each meal's name+ingredients against the allergy list,
    using the ALLERGEN_KEYWORDS expansion (dairy -> cheese, butter, paneer...)."""
    if not allergies:
        return []
    ids = [str(i) for i in meal_ids]
    marks = ",".join("?" * len(ids))
    with _connect() as con:
        rows = con.execute(f"SELECT id, name, LOWER(name || ' ' || ingredients) "
                           f"FROM meals WHERE id IN ({marks})", ids).fetchall()
    out = []
    for mid, name, text in rows:
        hits = []
        for a in allergies:
            a = a.strip().lower()
            if a and any(w in (text or "") for w in ALLERGEN_KEYWORDS.get(a, [a])):
                hits.append(a)
        if hits:
            out.append({"meal_id": mid, "name": name, "allergens_found": hits})
    return out