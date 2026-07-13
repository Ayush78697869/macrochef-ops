"""Snapshot the Airtable base -> data/airtable_snapshot.json -> data/ops.sqlite.

Online:   python -m src.snapshot_airtable
Offline:  python -m src.snapshot_airtable --offline    (no Airtable account needed:
          generates the same-shaped snapshot from dummy_data - used by CI/cloners)
"""
import json
import sqlite3
import sys
from pathlib import Path

SNAPSHOT = Path("data/airtable_snapshot.json")
OUT_DB = Path("data/ops.sqlite")


def fetch_snapshot():
    import os

    from dotenv import load_dotenv
    from pyairtable import Api
    load_dotenv()
    base = Api(os.environ["AIRTABLE_TOKEN"]).base(os.environ["AIRTABLE_BASE_ID"])
    # keep the exact Airtable API record shape: {id, createdTime, fields}
    return {t: [{"id": r["id"], "createdTime": r["createdTime"], "fields": r["fields"]}
                for r in base.table(t).all()]
            for t in ["Clients", "Meals", "Orders"]}


def fake_snapshot():
    """Same shape as the API response, generated locally (fixture mode)."""
    from src.dummy_data import generate
    snap = {}
    for tname, rows in generate().items():
        snap[tname] = [{"id": f"rec{tname[:3].upper()}{i:05d}",
                        "createdTime": "2026-07-01T00:00:00.000Z",
                        "fields": r} for i, r in enumerate(rows)]
    return snap


def load_to_sqlite(snap):
    OUT_DB.unlink(missing_ok=True)
    con = sqlite3.connect(OUT_DB)
    con.execute("""CREATE TABLE clients (id TEXT PRIMARY KEY, client_id TEXT,
        name TEXT, email TEXT, diet TEXT, allergies TEXT,
        calorie_target REAL, protein_target_g REAL, active INTEGER)""")
    con.execute("""CREATE TABLE meals (id TEXT PRIMARY KEY, meal_id TEXT,
        name TEXT, meal_type TEXT, calories REAL, protein_g REAL, carbs_g REAL,
        fat_g REAL, prep_minutes INTEGER, ingredients TEXT, rating REAL)""")
    con.execute("""CREATE TABLE orders (id TEXT PRIMARY KEY, order_id TEXT,
        client_id TEXT, meal_id TEXT, date TEXT, status TEXT)""")

    for r in snap["Clients"]:
        f = r["fields"]
        con.execute("INSERT INTO clients VALUES (?,?,?,?,?,?,?,?,?)",
                    (r["id"], f.get("Client ID"), f.get("Name"), f.get("Email"),
                     f.get("Diet", "none"), f.get("Allergies", ""),
                     f.get("Calorie Target"), f.get("Protein Target g"),
                     1 if f.get("Active") else 0))
    for r in snap["Meals"]:
        f = r["fields"]
        con.execute("INSERT INTO meals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (r["id"], f.get("Meal ID"), f.get("Name"), f.get("Meal Type"),
                     f.get("Calories"), f.get("Protein g"), f.get("Carbs g"),
                     f.get("Fat g"), f.get("Prep Minutes"),
                     f.get("Ingredients", ""), f.get("Rating")))
    for r in snap["Orders"]:
        f = r["fields"]
        con.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)",
                    (r["id"], f.get("Order ID"), f.get("Client ID"),
                     f.get("Meal ID"), f.get("Date"), f.get("Status")))
    con.execute("CREATE INDEX IF NOT EXISTS ix_meals_cal ON meals(calories)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_meals_prot ON meals(protein_g)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_meals_type ON meals(meal_type)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_orders_client ON orders(client_id)")
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["clients", "meals", "orders"]}
    print("ops.sqlite:", counts)


def main():
    snap = fake_snapshot() if "--offline" in sys.argv else fetch_snapshot()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=1), encoding="utf-8")
    print(f"snapshot: {SNAPSHOT} ({sum(len(v) for v in snap.values())} records)")
    load_to_sqlite(snap)


if __name__ == "__main__":
    main()