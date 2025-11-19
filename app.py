import os
import secrets
import traceback
from pathlib import Path

from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Carrega variáveis de ambiente
load_dotenv()

# ==========================================
# 1. CONFIGURAÇÕES
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

if os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = secrets.token_hex(16)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# ==========================================
# 2. MEMÓRIA GLOBAIS
# ==========================================
dados_globais = {
    'df': None,
    'nome_arquivo': ''
}
historicos = {}

# ==========================================
# 3. SELEÇÃO INTELIGENTE DE MODELO
# ==========================================
def obter_modelo_seguro():
    """
    Lista os modelos disponíveis para a chave e escolhe um SEGURO.
    Filtra modelos experimentais ('exp') para evitar erro de cota (429).
    Prioriza modelos 'flash' pela velocidade.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY não configurada.")
    
    genai.configure(api_key=api_key)
    
    candidatos = []
    try:
        # Pede ao Google o que está disponível PARA ESTA CONTA
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                nome = m.name.lower()
                # REGRA DE OURO: Fugir de modelos experimentais (Causa do erro 429)
                if 'exp' not in nome and 'experimental' not in nome:
                    candidatos.append(m.name)
    except Exception as e:
        # Se a listagem falhar, tenta o clássico 'gemini-pro' que quase nunca falha
        print(f"Erro ao listar modelos: {e}")
        return genai.GenerativeModel('gemini-pro')

    if not candidatos:
        # Se não sobrou nada (raro), tenta o padrãozão
        return genai.GenerativeModel('gemini-pro')

    # Lógica de escolha entre os candidatos seguros
    modelo_escolhido = None
    
    # 1. Tenta achar algum Flash (rápido e barato)
    for nome in candidatos:
        if 'flash' in nome:
            modelo_escolhido = nome
            break
    
    # 2. Se não tiver Flash, tenta o Pro 1.5
    if not modelo_escolhido:
        for nome in candidatos:
            if '1.5' in nome and 'pro' in nome:
                modelo_escolhido = nome
                break
                
    # 3. Se não tiver, pega o primeiro da lista limpa
    if not modelo_escolhido:
        modelo_escolhido = candidatos[0]

    print(f"🤖 Modelo Escolhido Automaticamente: {modelo_escolhido}")
    return genai.GenerativeModel(modelo_escolhido)


def gerar_prompt_analista(query, df, historico_chat):
    # Amostra de dados
    try:
        # Tenta usar Markdown (requer tabulate)
        amostra = df.head(8).to_markdown(index=False)
    except:
        # Fallback simples
        amostra = df.head(8).to_string(index=False)

    colunas = list(df.columns)
    
    # Estatísticas
    try:
        stats = df.describe().to_markdown()
    except:
        stats = "Estatísticas não disponíveis."

    # Histórico
    chat_context = ""
    if historico_chat:
        chat_context = "HISTÓRICO RECENTE:\n" + "\n".join(
            [f"{'User' if msg['role']=='user' else 'Bot'}: {msg['content']}" for msg in historico_chat[-4:]]
        )

    prompt = f"""
    Atue como o TheoBot, um Analista de Dados Sênior.
    
    DADOS DISPONÍVEIS:
    - Dimensões: {len(df)} linhas x {len(colunas)} colunas
    - Colunas: {', '.join(colunas)}
    
    ESTATÍSTICAS (Resumo Numérico):
    {stats}

    AMOSTRA (Primeiras 8 linhas):
    {amostra}

    {chat_context}

    PERGUNTA DO USUÁRIO: "{query}"

    DIRETRIZES:
    1. Seja direto, profissional e educado. Evite linguagem imprópria.
    2. Use formatação Markdown (Tabelas, Negrito) para organizar a resposta.
    3. Responda APENAS com base nos dados acima.
    """
    return prompt

# ==========================================
# 4. ROTAS
# ==========================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files: return jsonify({'success': False, 'message': 'Sem arquivo'}), 400
        file = request.files['file']
        if not file.filename: return jsonify({'success': False, 'message': 'Nome vazio'}), 400
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
            
        dados_globais['df'] = df.dropna(how='all')
        dados_globais['nome_arquivo'] = filename
        
        return jsonify({'success': True, 'message': 'Upload OK!', 'total_linhas': len(dados_globais['df'])})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Erro: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        # Checa memória
        if dados_globais['df'] is None:
            return jsonify({'success': False, 'response': '⚠️ Sessão reiniciada. Por favor, faça upload da planilha novamente.'}), 400

        data = request.get_json() or {}
        query = data.get('query')
        session_id = data.get('session_id') or 'default'
        
        if not query: return jsonify({'success': False, 'response': 'Pergunta vazia.'}), 400

        # CONFIGURAÇÃO SEGURA DO MODELO
        model = obter_modelo_seguro()
        
        # Histórico
        if session_id not in historicos: historicos[session_id] = []
        
        prompt = gerar_prompt_analista(query, dados_globais['df'], historicos[session_id])
        
        response = model.generate_content(prompt)
        texto_resp = response.text
        
        historicos[session_id].append({'role': 'user', 'content': query})
        historicos[session_id].append({'role': 'model', 'content': texto_resp})
        
        return jsonify({'success': True, 'response': texto_resp, 'session_id': session_id})

    except Exception as e:
        # Retorna erro detalhado no chat para debug se necessário
        print(traceback.format_exc())
        return jsonify({
            'success': False, 
            'response': f"❌ **Erro Técnico:** {str(e)}\n\n(Tentei selecionar um modelo seguro, mas houve falha na API ou na formatação)."
        }), 500

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({'status': 'online', 'dados': dados_globais['df'] is not None})

@app.route('/api/limpar', methods=['POST'])
def limpar():
    dados_globais['df'] = None
    return jsonify({'success': True})

@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(STATIC_DIR, path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)