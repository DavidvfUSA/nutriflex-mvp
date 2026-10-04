# NutriFlex MVP

## Rodar localmente
1. Instale Python 3.11+.
2. Abra o terminal nesta pasta.
3. Execute:
   pip install -r requirements.txt
   streamlit run app.py

## Publicar para testes
Suba os arquivos desta pasta para um repositório privado/público compatível com sua hospedagem e configure `app.py` como arquivo principal.

## Aviso
Protótipo experimental para testes. Não substitui nutricionista ou médico.
A autenticação local em SQLite é adequada somente para MVP controlado; antes de testes públicos amplos, migre usuários para um serviço de autenticação/banco apropriado.
