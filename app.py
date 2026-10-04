import streamlit as st
import sqlite3, json, time
from pathlib import Path
from supabase import create_client
from nutriflex_engine import Food, Target, PlanConfig, NutriFlexEngine, protein_target

BASE=Path(__file__).parent
FOOD_DB=BASE/"nutriflex_afcd_r3.sqlite"
st.set_page_config(page_title="NutriFlex",page_icon="🥗",layout="wide")

if "_supabase_client" not in st.session_state:
    st.session_state._supabase_client = create_client(
        st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    )
sb = st.session_state._supabase_client

def signup(email,pw): return sb.auth.sign_up({"email":email.strip().lower(),"password":pw})
def signin(email,pw): return sb.auth.sign_in_with_password({"email":email.strip().lower(),"password":pw})
def setauth(a):
    st.session_state.user=a.user; st.session_state.session=a.session
def logout():
    try: sb.auth.sign_out()
    finally: st.session_state.user=None; st.session_state.session=None
def save_profile(row):
    row={"user_id":str(st.session_state.user.id),**row}
    sb.table("profiles").upsert(row,on_conflict="user_id").execute()
def save_run(selected,targets,plan,totals,status,elapsed):
    tj={k:{"minimum":v.minimum,"maximum":v.maximum} for k,v in targets.items()}
    row={"user_id":str(st.session_state.user.id),"selected_foods":selected,
         "calculated_targets":tj,"generated_plan":plan,"nutrient_totals":totals,
         "result_status":status,"calculation_time_seconds":round(elapsed,4)}
    r=sb.table("test_runs").insert(row).execute()
    return r.data[0]["id"] if r.data else None
def save_feedback(run_id,rating,ease,comments):
    sb.table("feedback").insert({"user_id":str(st.session_state.user.id),
      "test_run_id":run_id,"plan_rating":rating,"ease_of_use_rating":ease,
      "comments":comments}).execute()

def food_rows(search="",limit=250):
    con=sqlite3.connect(FOOD_DB); con.row_factory=sqlite3.Row
    q=f"%{search}%"
    r=[dict(x) for x in con.execute("""SELECT food_key,food_name,food_name_pt,search_alias_pt,classification FROM foods
      WHERE lower(food_name) LIKE lower(?)
         OR lower(COALESCE(food_name_pt,'')) LIKE lower(?)
         OR lower(COALESCE(search_alias_pt,'')) LIKE lower(?)
      ORDER BY COALESCE(NULLIF(food_name_pt,''),food_name) LIMIT ?""",(q,q,q,limit))]
    con.close(); return r
def food_record(key):
    con=sqlite3.connect(FOOD_DB); con.row_factory=sqlite3.Row
    r=con.execute("""SELECT f.food_key,f.food_name,f.food_name_pt,f.classification,n.* FROM foods f
      JOIN nutrients_per_100g n USING(food_key) WHERE f.food_key=?""",(key,)).fetchone()
    con.close(); return dict(r) if r else None
def targets_for(sex,age,weight,calories,goal):
    male=sex=="Masculino"; prot=(1.8,2.0) if goal=="Ganho de massa muscular" else (1.2,1.6)
    fiber=38 if male and age<=50 else 30 if male else 25 if age<=50 else 21
    iron=8 if male else (18 if age<=50 else 8); magnesium=420 if male and age>=31 else 320
    potassium=3400 if male else 2600
    return {"energy_kcal":Target(calories*.95,calories*1.05),"protein_g":protein_target(weight,*prot),
      "fat_g":Target(calories*.20/9,calories*.35/9),"carb_g":Target(calories*.45/4,calories*.65/4),
      "fiber_g":Target(fiber,None),"calcium_mg":Target(1000,2500),"iron_mg":Target(iron,45),
      "magnesium_mg":Target(magnesium,None),"potassium_mg":Target(potassium,None),
      "sodium_mg":Target(None,2300),"zinc_mg":Target(11 if male else 8,40),
      "folate_ug":Target(400,None),"vitamin_c_mg":Target(90 if male else 75,2000),
      "vitamin_d_ug":Target(15,100)}
def build_foods(keys,meals):
    fs=("energy_kcal","protein_g","fat_g","carb_g","fiber_g","calcium_mg","iron_mg",
        "magnesium_mg","potassium_mg","sodium_mg","zinc_mg","folate_ug","vitamin_c_mg","vitamin_d_ug")
    out=[]
    for k in keys:
        r=food_record(k); n={x:float(r[x]) for x in fs if r.get(x) is not None}
        out.append(Food(r.get("food_name_pt") or r["food_name"],n,f"AFCD Release 3:{k}",tuple(meals),100,400,250,10))
    return out

st.title("🥗 NutriFlex — MVP de testes")
st.caption("Protótipo experimental. Não substitui avaliação de nutricionista ou médico.")
if "user" not in st.session_state: st.session_state.user=None
if "session" not in st.session_state: st.session_state.session=None
if not st.session_state.user:
    a,b=st.tabs(["Entrar","Criar cadastro"])
    with a:
        e=st.text_input("E-mail",key="le"); p=st.text_input("Senha",type="password",key="lp")
        if st.button("Entrar"):
            try: setauth(signin(e,p)); st.rerun()
            except Exception: st.error("Não foi possível entrar. Confira e-mail e senha.")
    with b:
        with st.form("signup_form", clear_on_submit=False):
            e=st.text_input("E-mail",key="re")
            p1=st.text_input("Senha",type="password",key="rp1")
            p2=st.text_input("Repita a senha",type="password",key="rp2")
            submitted=st.form_submit_button("Criar cadastro")
            if submitted:
                email=e.strip().lower()
                password=p1
                if not email or "@" not in email:
                    st.error("Informe um e-mail válido.")
                elif len(password)<8:
                    st.error(f"Use pelo menos 8 caracteres. A senha informada tem {len(password)}.")
                elif password!=p2:
                    st.error("As senhas não coincidem.")
                else:
                    try:
                        a=signup(email,password)
                        if a.session:
                            setauth(a)
                            st.rerun()
                        else:
                            st.success("Cadastro criado. Faça login.")
                    except Exception as ex:
                        st.error(f"Não foi possível criar o cadastro: {ex}")
    st.stop()

st.sidebar.write(f"**Usuário:** {st.session_state.user.email}")
if st.sidebar.button("Sair"): logout(); st.rerun()
st.subheader("1. Perfil")
c1,c2,c3,c4=st.columns(4)
sex=c1.selectbox("Sexo",["Masculino","Feminino"]); age=c2.number_input("Idade",18,90,39)
weight=c3.number_input("Peso (kg)",40.0,200.0,69.0,.5); height=c4.number_input("Altura (cm)",130,220,174)
activity=st.selectbox("Atividade",["Sedentário","Básico","Moderado","Ativo","Hiperativo"],index=3)
goal=st.selectbox("Objetivo",["Ganho de massa muscular","Manutenção"])
nmeals=st.slider("Número de refeições",3,5,4)
defaults=["07:00","12:00","16:00","19:00","21:00"][:nmeals]
times=st.text_input("Horários (separados por vírgula)",",".join(defaults))
meals=[x.strip() for x in times.split(",") if x.strip()]
if st.button("Salvar perfil"):
    try:
        save_profile({"sex":sex,"age":int(age),"weight_kg":float(weight),"height_cm":int(height),
          "activity_level":activity,"goal":goal,"meal_count":int(nmeals),"meal_times":meals})
        st.success("Perfil salvo.")
    except Exception as ex: st.error(f"Erro ao salvar perfil: {ex}")

bmr=10*weight+6.25*height-5*age+(5 if sex=="Masculino" else -161)
factor={"Sedentário":1.2,"Básico":1.35,"Moderado":1.5,"Ativo":1.65,"Hiperativo":1.8}[activity]
calories=bmr*factor+(150 if goal=="Ganho de massa muscular" else 0)
st.subheader("2. Alimentos disponíveis")

if "selected_foods" not in st.session_state:
    st.session_state.selected_foods = {}

show_raw = st.checkbox(
    "Mostrar alimentos crus",
    value=False,
    help="Ative se você costuma pesar carnes e outros alimentos antes do preparo."
)
search=st.text_input("Pesquisar alimentos",placeholder="Ex.: ovo, frango, arroz, lentilha...")
opts=food_rows(search)

def is_raw_food(row):
    text=((row.get("food_name") or "")+" "+(row.get("food_name_pt") or "")).lower()
    return any(term in text for term in (" raw", "cru", "uncooked", "não cozido"))

if not show_raw:
    opts=[r for r in opts if not is_raw_food(r)]

if search.strip():
    st.caption(f"Resultados para **{search.strip()}**")
    for i,r in enumerate(opts[:30]):
        label=r.get("food_name_pt") or r["food_name"]
        c1,c2=st.columns([6,1])
        c1.write(label)
        already=r["food_key"] in st.session_state.selected_foods
        if c2.button("✓" if already else "Adicionar",key=f"add_food_{r['food_key']}_{i}",disabled=already):
            st.session_state.selected_foods[r["food_key"]]=label
            st.rerun()
else:
    st.caption("Digite um alimento acima para pesquisar e adicionar.")

st.markdown("#### Meus alimentos disponíveis")
selected=st.session_state.selected_foods
st.caption(f"**{len(selected)} alimento(s) selecionado(s)**")

if selected:
    for i,(key,label) in enumerate(list(selected.items())):
        c1,c2=st.columns([6,1])
        c1.write(f"• {label}")
        if c2.button("Remover",key=f"remove_food_{key}_{i}"):
            del st.session_state.selected_foods[key]
            st.rerun()
    if st.button("Limpar lista",key="clear_foods"):
        st.session_state.selected_foods={}
        st.rerun()
else:
    st.info("Nenhum alimento adicionado ainda.")

keys=list(selected.keys())
chosen=list(selected.values())
st.info(f"Meta energética operacional estimada: **{calories:.0f} kcal/dia**.")
if st.button("Calcular plano",type="primary",disabled=(len(keys)<5 or len(meals)!=nmeals)):
    foods=build_foods(keys,meals); targets=targets_for(sex,age,weight,calories,goal)
    per=calories/len(meals); ranges={m:(per*.60,per*1.45) for m in meals}
    t0=time.perf_counter(); result=NutriFlexEngine(foods,PlanConfig(tuple(meals),targets,ranges,.03)).solve()
    elapsed=time.perf_counter()-t0; status=result["status"]; plan=result.get("plan",{})
    totals=result.get("validation",{}).get("totals",{})
    try:
        rid=save_run([{"food_key":k,"label":selected[k]} for k in keys],targets,plan,totals,status,elapsed)
        st.session_state.last_run_id=rid
    except Exception as ex: st.warning(f"Cálculo concluído, mas registro falhou: {ex}")
    if status!="VALID": st.error("Não foi possível montar um plano válido com os alimentos selecionados.")
    else:
        st.success("Plano nutricional válido.")
        for meal,items in plan.items():
            st.markdown(f"### {meal}")
            for name,g in items.items(): st.write(f"• {name}: **{g:.0f} g**")
        rows=[]
        for nutrient,t in targets.items():
            v=totals.get(nutrient,0); ok=(t.minimum is None or v>=t.minimum-1e-6) and (t.maximum is None or v<=t.maximum+1e-6)
            rows.append({"Nutriente":nutrient,"Total":round(v,1),"Mínimo":t.minimum,"Máximo":t.maximum,"Status":"🟢" if ok else "🔴"})
        st.dataframe(rows,use_container_width=True,hide_index=True)

if st.session_state.get("last_run_id"):
    st.divider(); st.subheader("3. Avalie este teste")
    with st.form("feedback"):
        rating=st.slider("Qualidade do plano",1,5,4); ease=st.slider("Facilidade de uso",1,5,4)
        comments=st.text_area("Comentários (opcional)")
        if st.form_submit_button("Enviar feedback"):
            try:
                save_feedback(st.session_state.last_run_id,rating,ease,comments)
                st.success("Feedback registrado."); st.session_state.last_run_id=None
            except Exception as ex: st.error(f"Erro ao registrar feedback: {ex}")
st.divider()
st.caption("Composição alimentar: Australian Food Composition Database (AFCD), Release 3.")
