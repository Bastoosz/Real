import os
import secrets
import traceback
from datetime import datetime
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
# 1. CONFIGURAÇÕES GERAIS
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Vercel exige escrita em /tmp
if os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. FLASK SETUP
# ==========================================
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = secrets.token_hex(16)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# ==========================================
# 3. MEMÓRIA DO SERVIDOR
# ==========================================
dados_globais = {
    'df': None,
    'nome_arquivo': ''
}
historicos = {}

# ==========================================
# 4. INTELIGÊNCIA ARTIFICIAL (CORRIGIDO)
# ==========================================

def obter_modelo_gemini():
    """
    Configura e retorna o modelo Gemini 1.5 Flash.
    Este modelo tem a melhor cota gratuita e velocidade.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("A GEMINI_API_KEY não foi configurada nas variáveis de ambiente.")
    
    genai.configure(api_key=api_key)
    
    # FORÇAMOS O MODELO CORRETO AQUI PARA EVITAR ERRO DE COTA (429)
    # O 'gemini-1.5-flash' é o mais estável para contas gratuitas.
    return genai.GenerativeModel('gemini-1.5-flash')

def gerar_prompt_analista(query, df, historico_chat):
    """
    Cria o prompt rico para o analista de dados
    """
    # Cria amostra dos dados
    try:
        # Tenta usar Markdown (requer tabulate no requirements.txt)
        amostra = df.head(8).to_markdown(index=False)
    except:
        # Fallback se der erro no tabulate
        amostra = df.head(8).to_string(index=False)

    colunas = list(df.columns)
    
    # Contexto estatístico
    try:
        stats = df.describe().to_markdown()
    except:
        stats = "Sem estatísticas numéricas."

    # Histórico
    chat_context = ""
    if historico_chat:
        chat_context = "HISTÓRICO RECENTE:\n" + "\n".join(
            [f"{'User' if msg['role']=='user' else 'Bot'}: {msg['content']}" for msg in historico_chat[-4:]]
        )

    prompt = f"""
    Você é o TheoBot, um Analista de Dados Sênior.
    
    TABELA DE DADOS:
    - Linhas: {len(df)} | Colunas: {', '.join(colunas)}
    
    ESTATÍSTICAS GERAIS:
    {stats}

    AMOSTRA (Primeiras 8 linhas):
    {amostra}

    {chat_context}

    PERGUNTA DO USUÁRIO: "{query}"

    REGRAS:
    1. Responda de forma profissional e direta.
    2. Use formatação Markdown (Negrito para números, Tabelas para listas).
    3. Baseie-se APENAS nos dados acima.
    4. Se houver datas, considere o formato brasileiro (dd/mm/aaaa).
    5. Não invente dados.
    """
    return prompt

# ==========================================
# 5. ROTAS
# ==========================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files: return jsonify({'success': False, 'message': 'Nenhum arquivo enviado.'}), 400
        file = request.files['file']
        if not file.filename: return jsonify({'success': False, 'message': 'Nome vazio.'}), 400
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
            
        dados_globais['df'] = df.dropna(how='all')
        dados_globais['nome_arquivo'] = filename
        
        return jsonify({
            'success': True, 
            'message': 'Upload realizado com sucesso!', 
            'total_linhas': len(dados_globais['df'])
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f"Erro no processamento: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        # Verifica Memória
        if dados_globais['df'] is None:
            return jsonify({
                'success': False, 
                'response': '⚠️ **Atenção:** O servidor reiniciou (comportamento padrão da Vercel). Por favor, faça o upload da planilha novamente.'
            }), 400

        data = request.get_json() or {}
        query = data.get('query')
        session_id = data.get('session_id') or 'sessao_padrao'
        
        if not query: return jsonify({'success': False, 'response': 'Pergunta vazia.'}), 400

        # Configura e Chama IA
        model = obter_modelo_gemini()
        
        if session_id not in historicos: historicos[session_id] = []
        prompt = gerar_prompt_analista(query, dados_globais['df'], historicos[session_id])
        
        response = model.generate_content(prompt)
        resposta_final = response.text
        
        # Salva histórico
        historicos[session_id].append({'role': 'user', 'content': query})
        historicos[session_id].append({'role': 'model', 'content': resposta_final})
        
        return jsonify({'success': True, 'response': resposta_final, 'session_id': session_id})

    except Exception as e:
        # Loga o erro no console da Vercel mas retorna JSON limpo
        print(traceback.format_exc()) 
        return jsonify({
            'success': False, 
            'response': f"❌ **Erro Técnico:** {str(e)}\n\nVerifique se a API Key é válida e se o arquivo requirements.txt contém 'google-generativeai>=0.7.0' e 'tabulate'."
        }), 500

@app.route('/api/status', methods=['GET'])
def status():
    tem_dados = dados_globais['df'] is not None
    return jsonify({
        'status': 'online',
        'dados': tem_dados,
        'arquivo': dados_globais.get('nome_arquivo')
    })

@app.route('/api/limpar', methods=['POST'])
def limpar():
    dados_globais['df'] = None
    return jsonify({'success': True})

# Rotas Frontend
@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(STATIC_DIR, path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)