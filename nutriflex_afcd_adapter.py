import sqlite3

NUTRIENT_FIELDS = (
    "energy_kcal","protein_g","fat_g","carb_g","fiber_g","calcium_mg","iron_mg",
    "magnesium_mg","potassium_mg","sodium_mg","zinc_mg","folate_ug","vitamin_c_mg","vitamin_d_ug"
)

def search_foods(db_path, text, limit=20):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT f.food_key, f.food_name, f.classification, f.derivation
           FROM foods f
           WHERE lower(f.food_name) LIKE lower(?)
           ORDER BY f.food_name LIMIT ?""",
        (f"%{text}%", limit)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

def get_food_record(db_path, food_key):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    r = con.execute(
        """SELECT f.*, n.*
           FROM foods f JOIN nutrients_per_100g n USING(food_key)
           WHERE f.food_key=?""", (food_key,)
    ).fetchone()
    con.close()
    return dict(r) if r else None

def to_engine_food(FoodClass, db_path, food_key, allowed_meals,
                   preferred_g, max_g_day, max_g_meal, step_g=10.0, excluded=False):
    r = get_food_record(db_path, food_key)
    if not r:
        raise KeyError(food_key)
    nutrients = {k: r[k] for k in NUTRIENT_FIELDS if r.get(k) is not None}
    return FoodClass(
        name=f"{r['food_name']} [{r['food_key']}]",
        nutrients_per_100g=nutrients,
        source=f"AFCD Release 3:{r['food_key']}",
        allowed_meals=tuple(allowed_meals),
        preferred_g=preferred_g,
        max_g_day=max_g_day,
        max_g_meal=max_g_meal,
        step_g=step_g,
        excluded=excluded
    )
