"""NutriFlex V3.2: otimização diária com grupos auditáveis e preferências flexíveis."""
import math
import re
import unicodedata
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

GROUPS = {
 'proteinas': ('Proteínas principais',1,3), 'cereais': ('Cereais',1,2),
 'tuberculos': ('Tubérculos',0,2), 'leguminosas': ('Leguminosas',1,3),
 'vegetais': ('Verduras e legumes',2,5), 'frutas': ('Frutas',1,3),
 'oleaginosas': ('Oleaginosas e sementes',0,2), 'gorduras': ('Gorduras e óleos',0,2),
 'temperos': ('Temperos e condimentos',0,5), 'laticinios': ('Laticínios e alternativas',0,2),
 'ovos': ('Ovos',0,1)
}

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(s).lower()) if not unicodedata.combining(c))

def food_group(name, category=''):
    """Prefer explicit curated category; conservative whole-word fallback for catalog search."""
    c=norm(category).strip(); s=norm(name)
    mapping={'proteinas - aves':'proteinas','proteinas - bovinos':'proteinas',
      'proteinas - suinos':'proteinas','peixes e frutos do mar':'proteinas',
      'cereais e paes':'cereais','tuberculos':'tuberculos','leguminosas':'leguminosas',
      'vegetais':'vegetais','frutas':'frutas','oleaginosas':'oleaginosas',
      'sementes':'oleaginosas','gorduras e complementos':'gorduras',
      'laticinios':'laticinios','bebidas vegetais':'laticinios','ovos':'ovos',
      'temperos e condimentos':'temperos'}
    if c in mapping:
        # Curated group is authoritative, except condiments misfiled as vegetables.
        if re.search(r'\b(alho|garlic|cebola|onion|salsa|parsley|coentro|coriander)\b',s): return 'temperos'
        return mapping[c]
    patterns=[
      ('temperos',r'\b(alho|garlic|cebola|onion|salsa|parsley|coentro|coriander|oregano|pimenta|pepper|basil|manjericao)\b'),
      ('ovos',r'\b(ovo|ovos|egg|eggs)\b'),
      ('tuberculos',r'\b(mandioca|cassava|batata|potato|inhame|yam|taro|sweet potato)\b'),
      ('leguminosas',r'\b(lentilha|lentil|feijao|bean|beans|chickpea|grao.de.bico|ervilha|peas)\b'),
      ('oleaginosas',r'\b(chia|linhaca|flax|semente|seed|castanha|cashew|amendoim|peanut|almond|nozes|walnut)\b'),
      ('gorduras',r'\b(azeite|olive oil|oleo|oil|manteiga|butter)\b'),
      ('laticinios',r'\b(iogurte|yogurt|yoghurt|leite|milk|queijo|cheese|cottage)\b'),
      ('proteinas',r'\b(frango|chicken|beef|bovina|porco|pork|salmao|salmon|peixe|fish|atum|tuna|sardinha|shrimp|camarao)\b'),
      ('cereais',r'\b(pao|bread|aveia|oat|arroz|rice|macarrao|massa|pasta|quinoa|milho|corn|cereal|wheat)\b'),
      ('frutas',r'\b(banana|maca|apple|kiwi|morango|strawberry|laranja|orange|manga|mango|uva|grape|abacaxi|pineapple|papaya|mamao|blueberry|melancia|watermelon)\b'),
      ('vegetais',r'\b(brocolis|broccoli|couve|kale|spinach|espinafre|cenoura|carrot|tomate|tomato|abobrinha|zucchini|pepino|cucumber|alface|lettuce|cabbage|repolho|cogumelo|mushroom)\b')]
    for g,pattern in patterns:
        if re.search(pattern,s):return g
    return None

def portion_limits(name, group):
    s=norm(name)
    if group=='temperos': return (2,20,1,5) if re.search(r'\b(alho|garlic)\b',s) else (5,50,5,15)
    if group=='gorduras':return (5,25,5,10)
    if group=='oleaginosas':return (10,40,5,25)
    if group=='laticinios':return (100,350,10,200)
    if group=='ovos':return (50,200,10,100)
    if group=='proteinas':return (80,250,10,150)
    if group=='vegetais':return (80,300,10,160)
    if group=='frutas':return (80,250,10,150)
    if group=='leguminosas':return (80,250,10,150)
    if group=='cereais' and re.search(r'\b(aveia|oat)\b',s):return (30,90,10,55)
    if group=='cereais' and re.search(r'\b(pao|bread)\b',s):return (30,120,10,70)
    if group=='cereais':return (60,250,10,150)
    if group=='tuberculos':return (80,250,10,150)
    raise ValueError('Grupo não classificado')

def optimize_daily(foods, targets, time_limit=35, food_categories=None, group_ranges=None):
    food_categories=food_categories or {}; group_ranges=group_ranges or {}
    foods=[f for f in foods if not f.excluded]
    if not foods:return {'status':'INFEASIBLE','reason':'Nenhum alimento disponível'}
    names=[f.name for f in foods]
    if len(set(names))!=len(names):return {'status':'INVALID','reason':'Nomes duplicados: não é seguro agregar quantidades.'}
    groups=[food_group(f.name,food_categories.get(f.source.split(':')[-1],'')) for f in foods]
    unknown=[f.name for f,g in zip(foods,groups) if g is None]
    # Unknown items must not be silently used with arbitrary limits.
    pairs=[(f,g) for f,g in zip(foods,groups) if g]
    if not pairs:return {'status':'INFEASIBLE','reason':'Nenhum alimento possui classificação funcional confiável.','warnings':unknown}
    foods,groups=map(list,zip(*pairs));n=len(foods)
    lim=[portion_limits(f.name,g) for f,g in zip(foods,groups)]
    steps=[v[2] for v in lim]; mins=[v[0] for v in lim]
    maxs=[min(v[1],f.max_g_day) for v,f in zip(lim,foods)]
    active=[g for g in GROUPS if g in groups]
    # x integer portions; y binary activation; slack for unmet preferred variety minima.
    N=2*n+len(active);c=np.zeros(N);lb=np.zeros(N);ub=np.zeros(N)
    for i in range(n):
        ub[i]=math.floor(maxs[i]/steps[i]);ub[n+i]=1
        c[i]=0.015*steps[i]/max(1,lim[i][3]);c[n+i]=0.09
    for j,g in enumerate(active):c[2*n+j]=30 if g in ('frutas','vegetais') else 12;ub[2*n+j]=GROUPS[g][2]
    rows=[];lo=[];hi=[]
    def add(terms,lower=-np.inf,upper=np.inf):
        row=np.zeros(N)
        for idx,val in terms:row[idx]+=val
        rows.append(row);lo.append(lower);hi.append(upper)
    for i in range(n):
        add([(i,steps[i]),(n+i,-maxs[i])],upper=0)
        add([(i,steps[i]),(n+i,-mins[i])],lower=0)
    for nutrient,t in targets.items():
        # Missing values are unknown, not measured zeros: report coverage below.
        terms=[(i,f.nutrients_per_100g.get(nutrient,0)*steps[i]/100) for i,f in enumerate(foods)]
        if t.minimum is not None:add(terms,lower=t.minimum)
        if t.maximum is not None:add(terms,upper=t.maximum)
    for j,g in enumerate(active):
        mn,mx=group_ranges.get(g,(GROUPS[g][1],GROUPS[g][2]))
        mn=int(mn);mx=int(mx)
        if not 0<=mn<=mx<=10:return {'status':'INVALID','reason':f'Intervalo inválido para {g}.'}
        ids=[n+i for i,v in enumerate(groups) if v==g]
        add([(i,1) for i in ids],upper=mx)
        add([(i,1) for i in ids]+[(2*n+j,1)],lower=mn)
    # No more than 2 simultaneous major starch types across cereals+tubers by default.
    starch=[n+i for i,g in enumerate(groups) if g in ('cereais','tuberculos')]
    if starch:add([(i,1) for i in starch],upper=3)
    try:
        r=milp(c=c,integrality=np.ones(N),bounds=Bounds(lb,ub),
            constraints=LinearConstraint(np.array(rows),lo,hi),
            options={'time_limit':time_limit,'mip_rel_gap':0.02})
    except Exception as exc:return {'status':'INVALID','reason':f'Falha no otimizador: {exc}'}
    if r.x is None:return {'status':'INFEASIBLE','reason':'Não foi encontrada solução nutricional viável com os alimentos e porções permitidos.','solver_message':r.message,'warnings':[f'Sem classificação: {v}' for v in unknown]}
    quantities={f.name:int(round(r.x[i]))*steps[i] for i,f in enumerate(foods) if round(r.x[i])>0}
    totals={k:sum(f.nutrients_per_100g.get(k,0)*quantities.get(f.name,0)/100 for f in foods) for k in targets}
    failures=[]
    for k,t in targets.items():
        v=totals[k]
        if t.minimum is not None and v<t.minimum-1e-4:failures.append(f'{k}: abaixo do mínimo')
        if t.maximum is not None and v>t.maximum+1e-4:failures.append(f'{k}: acima do máximo')
    for i,f in enumerate(foods):
        v=quantities.get(f.name,0)
        if v and not mins[i]<=v<=maxs[i]:failures.append(f'{f.name}: porção fora dos limites')
    count={g:sum(f.name in quantities for f,v in zip(foods,groups) if v==g) for g in GROUPS}
    warnings=[f'Sem classificação funcional: {v} (não utilizado).' for v in unknown]
    for g in GROUPS:
        mn,mx=group_ranges.get(g,(GROUPS[g][1],GROUPS[g][2]))
        if count[g]<mn:warnings.append(f'{GROUPS[g][0]}: {count[g]} de {mn} opções preferidas; mínimo flexibilizado.')
    for k in targets:
        missing=[f.name for f in foods if f.name in quantities and k not in f.nutrients_per_100g]
        if missing:warnings.append(f'{k}: dados ausentes em {len(missing)} alimento(s); total calculado pode estar incompleto.')
    if not r.success:failures.append('Solução encontrada, mas otimização não concluída: '+str(r.message))
    return {'status':'VALID' if not failures else 'INVALID','quantities':quantities,
      'validation':{'valid':not failures,'totals':totals,'failures':failures},
      'groups':[GROUPS[g][0] for g in GROUPS if count[g]],'group_counts':count,'warnings':warnings}
