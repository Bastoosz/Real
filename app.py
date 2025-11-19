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

# Carrega .env (local)
load_dotenv()

# --- CONFIGURAÇÕES ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
# Vercel exige uso de /tmp
UPLOAD_FOLDER = '/tmp' if os.environ.get('VERCEL') else os.path.join(BASE_DIR, 'uploads')
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = secrets.token_hex(16)
CORS(app, resources={r"/api/*": {"origins": "*"}})
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# --- VARIÁVEIS GLOBAIS ---
dados_globais = {'df': None, 'linhas': 0, 'cols': []}
historicos = {}

# --- FUNÇÕES AUXILIARES ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROTAS ---

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
            
        dados_globais['df'] = df
        dados_globais['linhas'] = len(df)
        dados_globais['cols'] = df.columns.tolist()
        
        return jsonify({'success': True, 'message': 'Carregado!', 'total_linhas': len(df)})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Erro Upload: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    # AQUI ESTÁ O SEGREDO DO DEBUG
    try:
        # 1. Tenta configurar o Gemini NA HORA DA MENSAGEM para pegar o erro
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            return jsonify({'success': False, 'response': 'ERRO: Variável GEMINI_API_KEY não encontrada na Vercel.'}), 500
            
        genai.configure(api_key=api_key)
        
        # 2. Tenta instanciar o modelo
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as model_error:
            return jsonify({'success': False, 'response': f'ERRO AO CRIAR MODELO: {str(model_error)}'}), 500

        # 3. Verifica dados
        if dados_globais['df'] is None:
            return jsonify({'success': False, 'response': '⚠️ Memória limpa. Faça upload novamente.'}), 400

        data = request.get_json() or {}
        query = data.get('query')
        if not query: return jsonify({'success': False, 'response': 'Pergunta vazia'}), 400

        # 4. Gera resposta
        df = dados_globais['df']
        prompt = f"Analise este dataframe com {len(df)} linhas. Colunas: {list(df.columns)}. Pergunta: {query}"
        
        response = model.generate_content(prompt)
        return jsonify({'success': True, 'response': response.text})

    except Exception as e:
        # PEGA O ERRO REAL E MOSTRA NO CHAT
        erro_detalhado = traceback.format_exc()
        print(erro_detalhado) # loga no console da Vercel
        return jsonify({'success': False, 'response': f"ERRO CRÍTICO PYTHON:\n{str(e)}\n\n{erro_detalhado[-200:]}"}), 500

# --- ROTAS FRONTEND ---
@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'): return jsonify({'error': 'Not found'}), 404
    return send_from_directory(STATIC_DIR, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

#asda