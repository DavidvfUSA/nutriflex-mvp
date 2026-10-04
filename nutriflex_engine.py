"""
NutriFlex Engine v0.1
Motor matemático de planejamento alimentar.

Dependência: scipy
Dados alimentares: carregar valores reais por 100 g de
TBCA/TACO/AFCD/CoFID/USDA. O motor não inventa valores ausentes.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import math
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

@dataclass
class Food:
    name: str
    nutrients_per_100g: Dict[str, float]
    source: str
    allowed_meals: Tuple[str, ...]
    preferred_g: float
    max_g_day: float
    max_g_meal: float
    step_g: float = 10.0
    excluded: bool = False

@dataclass
class Target:
    minimum: Optional[float] = None
    maximum: Optional[float] = None

@dataclass
class PlanConfig:
    meals: Tuple[str, ...]
    targets: Dict[str, Target]
    meal_energy_ranges: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    practicality_weight: float = 0.03

class NutriFlexEngine:
    def __init__(self, foods: List[Food], config: PlanConfig):
        self.foods = [f for f in foods if not f.excluded]
        self.config = config
        self.vars = [(fi, m) for fi, f in enumerate(self.foods)
                     for m in config.meals if m in f.allowed_meals]

    def _coef(self, f, nutrient):
        return f.nutrients_per_100g.get(nutrient, 0.0) * f.step_g / 100.0

    def solve(self):
        n = len(self.vars)
        if not n:
            return {"status": "INFEASIBLE", "reason": "No allowed foods"}

        c = np.zeros(n)
        lb = np.zeros(n)
        ub = np.zeros(n)
        integrality = np.ones(n)

        for j, (fi, _) in enumerate(self.vars):
            f = self.foods[fi]
            ub[j] = math.floor(f.max_g_meal / f.step_g)
            c[j] = self.config.practicality_weight * f.step_g / max(f.preferred_g, 1)

        rows, lows, highs = [], [], []

        for nutrient, target in self.config.targets.items():
            row = np.array([self._coef(self.foods[fi], nutrient)
                            for fi, _ in self.vars])
            if target.minimum is not None:
                rows.append(row); lows.append(target.minimum); highs.append(np.inf)
            if target.maximum is not None:
                rows.append(row); lows.append(-np.inf); highs.append(target.maximum)

        for fi, f in enumerate(self.foods):
            row = np.zeros(n)
            for j, (vfi, _) in enumerate(self.vars):
                if vfi == fi:
                    row[j] = f.step_g
            rows.append(row); lows.append(0); highs.append(f.max_g_day)

        for meal, (emin, emax) in self.config.meal_energy_ranges.items():
            row = np.zeros(n)
            for j, (fi, vm) in enumerate(self.vars):
                if vm == meal:
                    row[j] = self._coef(self.foods[fi], "energy_kcal")
            rows.append(row); lows.append(emin); highs.append(emax)

        constraints = LinearConstraint(np.vstack(rows), np.array(lows), np.array(highs))
        r = milp(c=c, integrality=integrality,
                 bounds=Bounds(lb, ub), constraints=constraints)

        if not r.success:
            return {"status": "INFEASIBLE", "message": r.message}

        plan = {m: {} for m in self.config.meals}
        for value, (fi, meal) in zip(r.x, self.vars):
            grams = round(value) * self.foods[fi].step_g
            if grams > 0:
                plan[meal][self.foods[fi].name] = grams

        validation = self.validate(plan)
        return {"status": "VALID" if validation["valid"] else "INVALID",
                "plan": plan, "validation": validation}

    def validate(self, plan):
        totals, daily = {}, {f.name: 0.0 for f in self.foods}
        fmap = {f.name: f for f in self.foods}
        failures = []

        for meal, items in plan.items():
            for name, grams in items.items():
                f = fmap[name]
                daily[name] += grams
                if grams > f.max_g_meal + 1e-9:
                    failures.append(f"{name}: limite por refeição excedido")
                for nutrient, amount in f.nutrients_per_100g.items():
                    totals[nutrient] = totals.get(nutrient, 0) + amount * grams / 100

        for f in self.foods:
            if daily[f.name] > f.max_g_day + 1e-9:
                failures.append(f"{f.name}: limite diário excedido")

        for nutrient, t in self.config.targets.items():
            v = totals.get(nutrient, 0)
            if t.minimum is not None and v + 1e-7 < t.minimum:
                failures.append(f"{nutrient}: abaixo do mínimo")
            if t.maximum is not None and v - 1e-7 > t.maximum:
                failures.append(f"{nutrient}: acima do máximo")

        return {"valid": not failures, "totals": totals, "failures": failures}

def protein_target(weight_kg, low_gkg=1.8, high_gkg=2.0):
    return Target(weight_kg * low_gkg, weight_kg * high_gkg)

def example_config():
    # Exemplo do perfil de teste. Acrescentar todos os micronutrientes
    # usando a tabela oficial de referência escolhida.
    return PlanConfig(
        meals=("07:00", "12:00", "16:00", "19:00"),
        targets={
            "energy_kcal": Target(2500, 2750),
            "protein_g": protein_target(69),
            "iron_mg": Target(8, 45),
        },
        meal_energy_ranges={
            "07:00": (400, 850),
            "12:00": (550, 950),
            "16:00": (250, 700),
            "19:00": (500, 950),
        }
    )

# Exemplo de uso:
# foods = [Food("Lentilha, cozida", {...dados reais...}, "TBCA:<id>",
#               ("12:00","19:00"), 100, 250, 150)]
# result = NutriFlexEngine(foods, example_config()).solve()
