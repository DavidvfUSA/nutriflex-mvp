"""NutriFlex V3.1: otimização diária com diversidade alimentar (experimental)."""
import math
import unicodedata
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

GROUPS=('vegetais','frutas','proteinas','leguminosas','cereais_tuberculos','laticinios','oleaginosas','gorduras','outros')

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(c))

def food_group(name,category=''):
    s=norm(name); c=norm(category)
    if any(x in c for x in ('hortalica','vegetai','verdura','legume -','vegetable')) or any(x in s for x in ('brocol','couve','kale','spinach','espinafre','cenoura','carrot','tomate','tomato','abobrinha','zucchini','pepino','cucumber','alface','lettuce','cabbage','repolho')):return 'vegetais'
    if 'fruta' in c or any(x in s for x in ('banana','maca','apple','kiwi','morango','strawberry','laranja','orange','manga','mango','uva','grape','abacaxi','pineapple','papaya','mamao','blueberry','melancia','watermelon')):return 'frutas'
    if any(x in c for x in ('leguminosa','feijoes')) or any(x in s for x in ('lentilha','lentil','feijao','beans','grao-de-bico','chickpea','ervilha','pea, cooked')):return 'leguminosas'
    if any(x in c for x in ('laticinio','leite','iogurte','queijo')) or any(x in s for x in ('iogurte','yogurt','leite','milk','queijo','cheese','cottage')):return 'laticinios'
    if any(x in c for x in ('oleaginosa','sementes','castanhas')) or any(x in s for x in ('chia','linhaca','flax','semente','seed','castanha','cashew','noz','almond','nut','amendoim','peanut')):return 'oleaginosas'
    if any(x in s for x in ('azeite','olive oil','oleo','oil','manteiga','butter')):return 'gorduras'
    if any(x in c for x in ('proteina','carnes','peixes','ovos','aves','bovinos','suinos')) or any(x in s for x in ('frango','chicken','beef','bovina','porco','pork','salmao','salmon','peixe','fish','atum','tuna','ovo','egg','sardinha')):return 'proteinas'
    if any(x in c for x in ('cereais','tuberculos','graos','paes')) or any(x in s for x in ('pao','bread','aveia','oat','arroz','rice','batata','potato','mandioca','cassava','inhame','yam','massa','pasta','quinoa','milho','corn')):return 'cereais_tuberculos'
    return 'outros'

def portion_limits(name,category=''):
    group=food_group(name,category);s=norm(name)
    if group=='gorduras':return (5,25,5,10)
    if group=='oleaginosas':return (10,40,5,25)
    if group=='laticinios':return (100,350,10,200)
    if 'ovo' in s or 'egg' in s:return (50,200,10,100)
    if group=='proteinas':return (80,250,10,150)
    if group=='vegetais':return (80,300,10,160)
    if group=='frutas':return (80,250,10,150)
    if group=='leguminosas':return (80,250,10,150)
    if 'pao' in s or 'bread' in s:return (30,120,10,70)
    if 'aveia' in s or 'oat' in s:return (30,90,10,55)
    if group=='cereais_tuberculos':return (80,250,10,150)
    return (40,200,10,100)

def optimize_daily(foods,targets,time_limit=35,food_categories=None):
    """MILP: nutrient bounds + realistic servings + diversity, never fabricates foods.

    Soft diversity encourages multiple food groups; vegetables and fruit become
    minimum groups only if the user has selected them. Missing groups are flagged.
    """
    food_categories=food_categories or {}
    foods=[f for f in foods if not f.excluded]
    if not foods:return {'status':'INFEASIBLE','reason':'Nenhum alimento disponível'}
    n=len(foods)
    names=[f.name for f in foods]
    if len(set(names))!=n:return {'status':'INVALID','reason':'Nomes duplicados; não é seguro agregar quantidades.'}
    groups=[food_group(f.name,food_categories.get(f.source.split(':')[-1],'')) for f in foods]
    lim=[portion_limits(f.name,food_categories.get(f.source.split(':')[-1],'')) for f in foods]
    mins=[v[0] for v in lim];maxs=[min(v[1],f.max_g_day) for v,f in zip(lim,foods)];steps=[v[2] for v in lim]
    group_names=[g for g in GROUPS if g in groups and g!='outros']
    k=len(group_names);N=2*n+k
    c=np.zeros(N)
    # y activation cost + gentle penalties for high portions, reward group coverage.
    for i in range(n):
        c[i]=0.025*steps[i]/max(1,lim[i][3])
        c[n+i]=0.16 if groups[i] not in ('vegetais','frutas','leguminosas') else 0.10
    for j,g in enumerate(group_names):c[2*n+j]=-0.32 if g in ('vegetais','frutas','leguminosas') else -0.20
    ub=[math.floor(maxs[i]/steps[i]) for i in range(n)]+[1]*(n+k)
    rows=[];lower=[];upper=[]
    def add(row,lo=-np.inf,hi=np.inf):rows.append(row);lower.append(lo);upper.append(hi)
    for i in range(n):
        row=np.zeros(N);row[i]=steps[i];row[n+i]=-maxs[i];add(row,hi=0)
        row=np.zeros(N);row[i]=-steps[i];row[n+i]=mins[i];add(row,hi=0)
    for nutrient,t in targets.items():
        row=np.zeros(N)
        for i,f in enumerate(foods):row[i]=f.nutrients_per_100g.get(nutrient,0)*steps[i]/100
        if t.minimum is not None:add(row,lo=t.minimum)
        if t.maximum is not None:add(row,hi=t.maximum)
    for j,g in enumerate(group_names):
        row=np.zeros(N);row[2*n+j]=-1
        for i in range(n):
            if groups[i]==g:row[n+i]=1
        add(row,lo=0) # group active if selected (z <= sum y)
        row=np.zeros(N);row[2*n+j]=-n
        for i in range(n):
            if groups[i]==g:row[n+i]=1
        add(row,hi=0) # sum y <= n*z
    # Vegetables and fruits should appear if offered; do not force missing foods.
    for g,minimum in (('vegetais',100),('frutas',100)):
        if g in groups:
            row=np.zeros(N)
            for i in range(n):
                if groups[i]==g:row[i]=steps[i]
            add(row,lo=minimum)
    # Avoid optimizing via too many competing starches, but allow two.
    if groups.count('cereais_tuberculos')>2:
        row=np.zeros(N)
        for i,g in enumerate(groups):
            if g=='cereais_tuberculos':row[n+i]=1
        add(row,hi=2)
    result=milp(c=c,integrality=np.ones(N),bounds=Bounds(np.zeros(N),ub),constraints=LinearConstraint(np.array(rows),lower,upper),options={'time_limit':time_limit,'mip_rel_gap':0.03})
    if result.x is None or not result.success:
        return {'status':'INFEASIBLE','reason':'Não foi possível comprovar uma solução com as metas, porções e diversidade exigidas. Experimente adicionar frutas, vegetais e outras fontes alimentares ou revisar as metas com um profissional.','solver_message':result.message}
    quantities={foods[i].name:int(round(result.x[i]))*steps[i] for i in range(n) if round(result.x[i])>0}
    totals={nutrient:sum(f.nutrients_per_100g.get(nutrient,0)*quantities.get(f.name,0)/100 for f in foods) for nutrient in targets}
    failures=[]
    for nutrient,t in targets.items():
        value=totals[nutrient]
        if t.minimum is not None and value<t.minimum-1e-5:failures.append(f'{nutrient}: abaixo da meta')
        if t.maximum is not None and value>t.maximum+1e-5:failures.append(f'{nutrient}: acima da meta')
    for i,f in enumerate(foods):
        grams=quantities.get(f.name,0)
        if grams and (grams<mins[i] or grams>maxs[i]):failures.append(f'{f.name}: porção fora dos limites')
    used_groups=sorted({groups[i] for i,f in enumerate(foods) if f.name in quantities})
    missing=[g for g in ('vegetais','frutas','leguminosas') if g not in groups]
    warnings=[f'Grupo não disponível na lista selecionada: {g}.' for g in missing]
    return {'status':'VALID' if not failures else 'INVALID','quantities':quantities,'validation':{'valid':not failures,'totals':totals,'failures':failures},'groups':used_groups,'warnings':warnings}
