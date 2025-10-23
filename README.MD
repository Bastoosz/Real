🤖 TheoBot

Meu primeiro projeto grande: um chatbot que analisa planilhas usando IA.
O que ele faz?

Você faz upload de uma planilha e pode conversar com ela fazendo perguntas em português. O bot usa o Google Gemini para entender e responder.
Tecnologias

Backend: Python, Flask, Pandas
IA: Google Gemini API
Frontend: HTML, CSS, JavaScript

Como rodar

Backend

bashcd backend
python -m venv venv
venv\Scripts\activate  # Windows

pip install -r requirements.txt

Crie um arquivo .env com sua chave do Gemini:
GEMINI_API_KEY=sua_chave_aqui

bashpython app.py

Frontend
Abra o arquivo frontend/index.html no navegador.

Funcionalidades

✅ Carrega múltiplas planilhas automaticamente
✅ Upload de novas planilhas
✅ Histórico de conversas
✅ Interface responsiva

Observações

Este é meu primeiro projeto grande e ainda estou aprendendo. Qualquer feedback é bem-vindo!