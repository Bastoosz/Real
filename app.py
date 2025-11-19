import os
import secrets
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
# 1. CONFIGURAÇÕES DE DIRETÓRIO
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Na Vercel, usamos /tmp para arquivos temporários
if os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. INICIALIZAÇÃO DO FLASK
# ==========================================
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = secrets.token_hex(16)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# ==========================================
# 3. CONFIGURAÇÃO DO GEMINI (CORRIGIDO)
# ==========================================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
model = None  # Inicializa como None para não quebrar o código depois

if not GEMINI_API_KEY:
    print("⚠️ CRÍTICO: GEMINI_API_KEY não encontrada nas variáveis de ambiente!")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ Gemini configurado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao configurar Gemini: {e}")

# ==========================================
# 4. DADOS GLOBAIS
# ==========================================
dados_globais = {
    'dataframe': None,
    'arquivos_carregados': [],
    'total_linhas': 0,
    'colunas': [],
    'data_carga': None
}
historicos = {}

# ==========================================
# 5. FUNÇÕES AUXILIARES
# ==========================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def adicionar_nova_planilha(filepath, filename):
    try:
        extensao = filename.lower().split('.')[-1]
        df_novo = None
        
        if extensao == 'csv':
            df_novo = pd.read_csv(filepath, encoding='utf-8')
        elif extensao in ['xlsx', 'xls']:
            df_novo = pd.read_excel(filepath)
        
        if df_novo is None:
            return False, "Formato não suportado."
            
        df_novo = df_novo.dropna(how='all')
        
        if dados_globais['dataframe'] is not None:
            df_completo = pd.concat([dados_globais['dataframe'], df_novo], ignore_index=True)
            df_completo = df_completo.drop_duplicates()
        else:
            df_completo = df_novo
            
        dados_globais['dataframe'] = df_completo
        if filename not in dados_globais['arquivos_carregados']:
            dados_globais['arquivos_carregados'].append(filename)
        dados_globais['total_linhas'] = len(df_completo)
        dados_globais['colunas'] = df_completo.columns.tolist()
        dados_globais['data_carga'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return True, f"Carregado! Total linhas: {len(df_completo)}"
    except Exception as e:
        return False, f"Erro: {str(e)}"

def criar_contexto_ia(session_id=None):
    if dados_globais['dataframe'] is None:
        return "Não há dados carregados. Peça para o usuário fazer upload de uma planilha."
    
    df = dados_globais['dataframe']
    amostra = df.head(5).to_string(index=False)
    
    contexto = f"""
    Atue como analista de dados.
    DADOS: {len(df)} linhas, Colunas: {', '.join(df.columns.tolist())}
    AMOSTRA: {amostra}
    """
    return contexto

# ==========================================
# 6. ROTAS DA API
# ==========================================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Sem arquivo'}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Arquivo inválido'}), 400

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        success, msg = adicionar_nova_planilha(filepath, filename)
        if success:
            return jsonify({'success': True, 'message': msg, 'total_linhas': dados_globais['total_linhas']})
        return jsonify({'success': False, 'message': msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    # 1. Verifica se o modelo foi carregado
    if model is None:
        return jsonify({
            'success': False, 
            'response': 'ERRO: A IA não foi configurada corretamente no servidor (API Key ausente ou inválida).'
        }), 500

    # 2. Verifica se há dados carregados
    if dados_globais['dataframe'] is None:
        return jsonify({
            'success': False, 
            'response': 'Por favor, faça o upload da planilha novamente (os dados são limpos periodicamente no servidor).'
        }), 400

    data = request.get_json() or {}
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'success': False, 'response': 'Digite uma pergunta.'}), 400

    if 'session_id' not in session: session['session_id'] = secrets.token_hex(8)
    session_id = session['session_id']

    try:
        contexto = criar_contexto_ia(session_id)
        prompt = f"{contexto}\n\nUSUÁRIO: {query}\nRESPOSTA:"
        
        response = model.generate_content(prompt)
        resposta_bot = response.text
        
        if session_id not in historicos: historicos[session_id] = []
        historicos[session_id].append({'pergunta': query, 'resposta': resposta_bot})
        
        return jsonify({'success': True, 'response': resposta_bot, 'session_id': session_id})
    except Exception as e:
        print(f"Erro no Chat: {e}")
        return jsonify({'success': False, 'response': f"Erro ao processar: {str(e)}"}), 500

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'online',
        'ai_configured': model is not None,
        'linhas': dados_globais['total_linhas']
    })

@app.route('/api/limpar_historico', methods=['POST'])
def limpar():
    if 'session_id' in session: historicos.pop(session['session_id'], None)
    return jsonify({'success': True})

# ==========================================
# 7. ROTAS DO FRONTEND
# ==========================================
@app.route('/')
def index():
    if not os.path.exists(os.path.join(STATIC_DIR, 'index.html')):
        return f"Erro: index.html não encontrado em {STATIC_DIR}", 404
    return send_from_directory(STATIC_DIR, 'index.html')

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint não encontrado'}), 404
    return send_from_directory(STATIC_DIR, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)