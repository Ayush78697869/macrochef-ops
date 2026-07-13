"""Generate dummy ops data: clients (Faker), meals (synthetic - or curated from
public recipes, see Appendix A), and orders. Nothing here touches prod anything.
Sanity check:  python -m src.dummy_data
"""
import json
import random
import sqlite3

from faker import Faker

random.seed(42)          # reproducible dummy data
fake = Faker()
Faker.seed(42)

DIETS = ["none", "vegetarian", "vegan", "gluten-free", "low-carb"]
ALLERGENS = ["peanut", "tree nut", "dairy", "egg", "soy", "shellfish", "wheat", "sesame"]
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]

# ---------------- Clients ----------------

def make_clients(n=25):
    clients = []
    for i in range(n):
        cal = random.choice(range(1500, 3001, 100))
        clients.append({
            "Client ID": f"CL-{1000 + i}",
            "Name": fake.name(),
            "Email": fake.unique.email(),           # Faker = fake people only
            "Diet": random.choices(DIETS, weights=[50, 20, 10, 10, 10])[0],
            "Allergies": ", ".join(sorted(random.sample(ALLERGENS, k=random.choices(
                [0, 1, 2], weights=[55, 30, 15])[0]))),
            "Calorie Target": cal,
            "Protein Target g": int(cal * random.uniform(0.20, 0.30) / 4),
            "Active": random.random() < 0.85,
        })
    return clients

# ---------------- Meals (synthetic; Appendix A swaps in real public recipes) ----

def synthetic_meals(n=600):
    proteins = ["chicken", "paneer", "tofu", "salmon", "chickpea", "turkey",
                "black bean", "egg", "shrimp", "lentil"]
    styles = ["bowl", "wrap", "salad", "stir fry", "curry", "skillet",
              "sandwich", "tacos", "soup", "plate"]
    extras = ["brown rice", "quinoa", "spinach", "sweet potato", "avocado",
              "greek yogurt", "peanut sauce", "cheddar", "sesame dressing", "noodles"]
    macro_ranges = {  # (calories, protein_g) sampling ranges per meal type
        "breakfast": ((250, 550), (10, 35)), "lunch": ((400, 800), (20, 55)),
        "dinner": ((450, 900), (25, 60)), "snack": ((100, 350), (5, 25)),
    }
    meals, per_type = [], n // len(MEAL_TYPES)
    for mt in MEAL_TYPES:
        (c_lo, c_hi), (p_lo, p_hi) = macro_ranges[mt]
        for j in range(per_type):
            prot, extra = random.choice(proteins), random.choice(extras)
            cal = random.randint(c_lo, c_hi)
            p = random.randint(p_lo, p_hi)
            f = round(random.uniform(0.15, 0.40) * cal / 9, 1)
            carbs = round(max(cal - p * 4 - f * 9, 0) / 4, 1)
            meals.append({
                "Meal ID": f"M-{mt[:2].upper()}{j:03d}",
                "Name": f"{prot.title()} {random.choice(styles)} with {extra}",
                "Meal Type": mt,
                "Calories": cal, "Protein g": p, "Carbs g": carbs, "Fat g": f,
                "Prep Minutes": random.randint(5, 45),
                "Ingredients": f"{prot}, {extra}, olive oil, garlic, salt",
                "Rating": round(random.uniform(3.5, 5.0), 2),
            })
    return meals


def curate_meals_from_foodcom(db="data/recipes.sqlite", n=600):
    """Optional (Appendix A): pick top-rated real public recipes instead."""
    con = sqlite3.connect(db)
    meals, per_type = [], n // len(MEAL_TYPES)
    type_tag = {"breakfast": "breakfast", "lunch": "lunch",
                "dinner": "dinner", "snack": "snacks"}
    for mt in MEAL_TYPES:
        rows = con.execute(
            """SELECT name, calories, protein_g, carbs_g, fat_g, minutes,
                      ingredients, rating
               FROM recipes
               WHERE tags LIKE ? AND n_ratings >= 10
                 AND calories BETWEEN 150 AND 1200
               ORDER BY rating DESC, n_ratings DESC LIMIT ?""",
            (f"%{type_tag[mt]}%", per_type)).fetchall()
        for j, r in enumerate(rows):
            meals.append({
                "Meal ID": f"M-{mt[:2].upper()}{j:03d}",
                "Name": r[0].title(),
                "Meal Type": mt,
                "Calories": r[1], "Protein g": r[2], "Carbs g": r[3], "Fat g": r[4],
                "Prep Minutes": r[5],
                "Ingredients": ", ".join(json.loads(r[6])),
                "Rating": r[7],
            })
    return meals

# ---------------- Orders ----------------

def make_orders(clients, meals, n=300):
    orders = []
    for i in range(n):
        c, m = random.choice(clients), random.choice(meals)
        orders.append({
            "Order ID": f"O-{20000 + i}",
            "Client ID": c["Client ID"],
            "Meal ID": m["Meal ID"],
            "Date": fake.date_between(start_date="-60d", end_date="+7d").isoformat(),
            "Status": random.choices(["delivered", "scheduled", "skipped"],
                                     weights=[70, 25, 5])[0],
        })
    return orders


def generate(use_foodcom=False):
    clients = make_clients()
    meals = curate_meals_from_foodcom() if use_foodcom else synthetic_meals()
    return {"Clients": clients, "Meals": meals,
            "Orders": make_orders(clients, meals)}


if __name__ == "__main__":
    data = generate()
    for table, rows in data.items():
        print(f"{table}: {len(rows)} rows | sample: {json.dumps(rows[0])[:120]}")