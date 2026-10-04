
import streamlit as st
import sqlite3, hashlib, json, math
from pathlib import Path
from nutriflex_engine import Food, Target, PlanConfig, NutriFlexEngine, protein_target

BASE = Path(__file__).parent
FOOD_DB = BASE / "nutriflex_afcd_r3.sqlite"
USER_DB = BASE / "nutriflex_users.sqlite"

st.set_page_config(page_title="NutriFlex MVP", page_icon="🥗", layout="wide")

def db_users():
    con=sqlite3.connect(USER_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL, profile_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit()
    return con

def phash(p): return hashlib.sha256(("nutriflex-mvp:"+p).encode()).hexdigest()

def register(email,pwd):
    try:
        con=db_users(); con.execute("INSERT INTO users(email,password_hash) VALUES(?,?)",(email.lower().strip(),phash(pwd)))
        con.commit(); con.close(); return True
    except sqlite3.IntegrityError: return False

def login(email,pwd):
    con=db_users(); r=con.execute("SELECT id,email,profile_json FROM users WHERE email=? AND password_hash=?",
                                  (email.lower().strip(),phash(pwd))).fetchone(); con.close()
    return r

def save_profile(uid,p):
    con=db_users(); con.execute("UPDATE users SET profile_json=? WHERE id=?",(json.dumps(p),uid)); con.commit(); con.close()

def food_rows(search="", limit=250):
    con=sqlite3.connect(FOOD_DB)
    con.row_factory=sqlite3.Row
    q="""SELECT f.food_key,f.food_name,f.classification FROM foods f
         WHERE lower(f.food_name) LIKE lower(?) ORDER BY f.food_name LIMIT ?"""
    rows=[dict(x) for x in con.execute(q,(f"%{search}%",limit)).fetchall()]
    con.close(); return rows

def food_record(key):
    con=sqlite3.connect(FOOD_DB); con.row_factory=sqlite3.Row
    r=con.execute("""SELECT f.food_key,f.food_name,f.classification,n.*
                     FROM foods f JOIN nutrients_per_100g n USING(food_key)
                     WHERE f.food_key=?""",(key,)).fetchone()
    con.close(); return dict(r) if r else None

def targets_for(sex, age, weight, calories, goal):
    # MVP adulto: referências operacionais já usadas/validadas no protótipo.
    # Não inventa UL para nutrientes em que o limite aplicável não é de alimento total.
    male = sex=="Masculino"
    protein=(1.8,2.0) if goal=="Ganho de massa muscular" else (1.2,1.6)
    fiber=38 if male and age<=50 else 30 if male else 25 if age<=50 else 21
    iron=8 if male else (18 if age<=50 else 8)
    magnesium=420 if male and age>=31 else 320
    potassium=3400 if male else 2600
    fat_lo,fat_hi=calories*.20/9, calories*.35/9
    carb_lo,carb_hi=calories*.45/4, calories*.65/4
    return {
      "energy_kcal":Target(calories*.95, calories*1.05),
      "protein_g":protein_target(weight,*protein),
      "fat_g":Target(fat_lo,fat_hi),"carb_g":Target(carb_lo,carb_hi),
      "fiber_g":Target(fiber,None),"calcium_mg":Target(1000,2500),
      "iron_mg":Target(iron,45),"magnesium_mg":Target(magnesium,None),
      "potassium_mg":Target(potassium,None),"sodium_mg":Target(None,2300),
      "zinc_mg":Target(11 if male else 8,40),"folate_ug":Target(400,None),
      "vitamin_c_mg":Target(90 if male else 75,2000),"vitamin_d_ug":Target(15,100)
    }

def build_foods(keys, meals):
    out=[]
    fields=("energy_kcal","protein_g","fat_g","carb_g","fiber_g","calcium_mg","iron_mg",
            "magnesium_mg","potassium_mg","sodium_mg","zinc_mg","folate_ug","vitamin_c_mg","vitamin_d_ug")
    for k in keys:
        r=food_record(k)
        if not r: continue
        nutrients={x:float(r[x]) for x in fields if r.get(x) is not None}
        out.append(Food(r["food_name"],nutrients,f"AFCD Release 3:{k}",tuple(meals),
                        preferred_g=100,max_g_day=400,max_g_meal=250,step_g=10))
    return out

if "user" not in st.session_state: st.session_state.user=None
st.title("🥗 NutriFlex — MVP de testes")
st.caption("Protótipo experimental. Não substitui avaliação de nutricionista ou médico.")

if not st.session_state.user:
    a,b=st.tabs(["Entrar","Criar cadastro"])
    with a:
        email=st.text_input("E-mail",key="le"); pwd=st.text_input("Senha",type="password",key="lp")
        if st.button("Entrar"):
            r=login(email,pwd)
            if r: st.session_state.user={"id":r[0],"email":r[1],"profile":json.loads(r[2]) if r[2] else {}}; st.rerun()
            else: st.error("E-mail ou senha inválidos.")
    with b:
        email=st.text_input("E-mail",key="re"); p1=st.text_input("Senha",type="password",key="rp1")
        p2=st.text_input("Repita a senha",type="password",key="rp2")
        if st.button("Criar cadastro"):
            if len(p1)<6: st.error("Use pelo menos 6 caracteres.")
            elif p1!=p2: st.error("As senhas não coincidem.")
            elif register(email,p1): st.success("Cadastro criado. Entre na aba Entrar.")
            else: st.error("E-mail já cadastrado.")
    st.stop()

u=st.session_state.user
st.sidebar.write(f"**Usuário:** {u['email']}")
if st.sidebar.button("Sair"): st.session_state.user=None; st.rerun()

with st.form("profile"):
    st.subheader("1. Perfil")
    c1,c2,c3,c4=st.columns(4)
    sex=c1.selectbox("Sexo",["Masculino","Feminino"])
    age=c2.number_input("Idade",18,90,39)
    weight=c3.number_input("Peso (kg)",40.0,200.0,69.0,0.5)
    height=c4.number_input("Altura (cm)",130,220,174)
    activity=st.selectbox("Atividade",["Sedentário","Básico","Moderado","Ativo","Hiperativo"],index=3)
    goal=st.selectbox("Objetivo",["Ganho de massa muscular","Manutenção"])
    nmeals=st.slider("Número de refeições",3,5,4)
    default_times=["07:00","12:00","16:00","19:00","21:00"][:nmeals]
    times=st.text_input("Horários (separados por vírgula)",",".join(default_times))
    submitted=st.form_submit_button("Salvar perfil")
    if submitted:
        p={"sex":sex,"age":age,"weight":weight,"height":height,"activity":activity,"goal":goal,"times":times}
        save_profile(u["id"],p); st.success("Perfil salvo.")

# Mifflin-St Jeor + fator operacional do MVP
bmr=10*weight+6.25*height-5*age+(5 if sex=="Masculino" else -161)
factor={"Sedentário":1.2,"Básico":1.35,"Moderado":1.5,"Ativo":1.65,"Hiperativo":1.8}[activity]
calories=bmr*factor + (150 if goal=="Ganho de massa muscular" else 0)
meals=[x.strip() for x in times.split(",") if x.strip()]
if len(meals)!=nmeals: st.warning("Informe exatamente um horário por refeição.")

st.subheader("2. Alimentos disponíveis")
search=st.text_input("Pesquisar alimentos AFCD",placeholder="Ex.: egg, chicken, rice, lentil...")
opts=food_rows(search,250)
labels={f"{r['food_name']} — {r['food_key']}":r["food_key"] for r in opts}
selected_labels=st.multiselect("Selecione os alimentos que você tem acesso",list(labels.keys()))
keys=[labels[x] for x in selected_labels]

st.info(f"Meta energética operacional estimada para este teste: **{calories:.0f} kcal/dia**.")
if st.button("Calcular plano",type="primary",disabled=(len(keys)<5 or len(meals)!=nmeals)):
    foods=build_foods(keys,meals)
    targets=targets_for(sex,age,weight,calories,goal)
    per=calories/len(meals)
    ranges={m:(per*.60,per*1.45) for m in meals}
    cfg=PlanConfig(tuple(meals),targets,ranges,0.03)
    with st.spinner("Calculando..."):
        result=NutriFlexEngine(foods,cfg).solve()
    if result["status"]!="VALID":
        st.error("Não foi possível montar um plano válido com os alimentos selecionados e os limites atuais.")
    else:
        st.success("Plano nutricional válido.")
        for meal,items in result["plan"].items():
            st.markdown(f"### {meal}")
            if not items: st.write("—")
            for name,g in items.items(): st.write(f"• {name}: **{g:.0f} g**")
        st.subheader("Resumo nutricional diário")
        totals=result["validation"]["totals"]
        rows=[]
        for nutrient,t in targets.items():
            v=totals.get(nutrient,0)
            ok=(t.minimum is None or v>=t.minimum-1e-6) and (t.maximum is None or v<=t.maximum+1e-6)
            rows.append({"Nutriente":nutrient,"Total":round(v,1),
                         "Mínimo":None if t.minimum is None else round(t.minimum,1),
                         "Máximo":None if t.maximum is None else round(t.maximum,1),
                         "Status":"🟢" if ok else "🔴"})
        st.dataframe(rows,use_container_width=True,hide_index=True)

st.divider()
st.caption("Dados de composição alimentar: Australian Food Composition Database (AFCD), Release 3. MVP para testes de produto.")
