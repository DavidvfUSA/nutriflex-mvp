"""Otimizador diário NutriFlex V3. Não cria refeições nem substitui orientação clínica."""
import math
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint


def portion_limits(name):
    s=name.casefold()
    if any(x in s for x in ('azeite','óleo','oil','manteiga','butter')): return 5,30,5
    if any(x in s for x in ('chia','linhaça','semente','seed','castanha','noz','almond','nut','amendoim')): return 10,60,5
    if any(x in s for x in ('sal','salt','tempero','spice')): return 0,0,5
    if any(x in s for x in ('pão','bread','torrada','toast')): return 30,160,10
    if any(x in s for x in ('aveia','oat','flocos')): return 30,100,10
    if any(x in s for x in ('ovo','egg')): return 50,200,10
    if any(x in s for x in ('frango','chicken','beef','bovina','porco','pork','salmão','salmon','peixe','fish','atum','tuna')): return 80,250,10
    if any(x in s for x in ('leite','milk','iogurte','yogurt','bebida','drink')): return 100,350,10
    if any(x in s for x in ('arroz','rice','batata','potato','mandioca','cassava','lentilha','lentil','feijão','bean','massa','pasta')): return 80,300,10
    if any(x in s for x in ('banana','maçã','apple','uva','grape','kiwi','morango','berry','laranja','orange','manga','mango')): return 60,250,10
    return 40,250,10


def optimize_daily(foods,targets,time_limit=20):
    """Mixed integer program with on/off food portions and validated daily totals."""
    foods=[f for f in foods if not f.excluded]
    if not foods: return {'status':'INFEASIBLE','reason':'Nenhum alimento disponível'}
    n=len(foods); mins=[]; maxs=[]; steps=[]
    for f in foods:
        low,high,step=portion_limits(f.name)
        high=min(high,f.max_g_day)
        mins.append(low); maxs.append(high); steps.append(step)
    # x = servings of step grams; y = whether food is used
    obj=np.array([0.0005*steps[i]/max(100,foods[i].preferred_g) for i in range(n)]+[0.35]*n)
    bounds=Bounds(np.zeros(2*n),np.array([math.floor(maxs[i]/steps[i]) for i in range(n)]+[1]*n,dtype=float))
    rows=[]; lower=[]; upper=[]
    for i in range(n):
        row=np.zeros(2*n);row[i]=steps[i];row[n+i]=-maxs[i]
        rows.append(row);lower.append(-np.inf);upper.append(0)
        row=np.zeros(2*n);row[i]=-steps[i];row[n+i]=mins[i]
        rows.append(row);lower.append(-np.inf);upper.append(0)
    for nutrient,t in targets.items():
        row=np.zeros(2*n)
        for i,f in enumerate(foods): row[i]=f.nutrients_per_100g.get(nutrient,0)*steps[i]/100
        if t.minimum is not None: rows.append(row.copy());lower.append(t.minimum);upper.append(np.inf)
        if t.maximum is not None: rows.append(row.copy());lower.append(-np.inf);upper.append(t.maximum)
    result=milp(c=obj,integrality=np.ones(2*n),bounds=bounds,constraints=LinearConstraint(np.array(rows),lower,upper),options={'time_limit':time_limit})
    if result.x is None or not result.success:
        return {'status':'INFEASIBLE','reason':'Nenhuma solução comprovadamente viável com os limites atuais; ou tempo de cálculo esgotado.'}
    quantities={foods[i].name:round(result.x[i])*steps[i] for i in range(n) if round(result.x[i])*steps[i]>0}
    totals={k:sum(f.nutrients_per_100g.get(k,0)*quantities.get(f.name,0)/100 for f in foods) for k in targets}
    failures=[]
    for k,t in targets.items():
        v=totals[k]
        if t.minimum is not None and v<t.minimum-1e-5:failures.append(f'{k}: abaixo da meta')
        if t.maximum is not None and v>t.maximum+1e-5:failures.append(f'{k}: acima do limite')
    for i,f in enumerate(foods):
        g=quantities.get(f.name,0)
        if g and (g<mins[i] or g>maxs[i]):failures.append(f'{f.name}: porção inválida')
    return {'status':'VALID' if not failures else 'INVALID','quantities':quantities,'validation':{'valid':not failures,'totals':totals,'failures':failures}}
