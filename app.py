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

load_dotenv()

# --- CONFIGURAÇÕES ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOAD_FOLDER = '/tmp' if os.environ.get('VERCEL') else os.path.join(BASE_DIR, 'uploads')
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = secrets.token_hex(16)
CORS(app, resources={r"/api/*": {"origins": "*"}})
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# --- DADOS GLOBAIS ---
dados_globais = {'df': None, 'linhas': 0, 'cols': []}
historicos = {}

# --- FUNÇÃO MÁGICA: ENCONTRAR MODELO ---
def configurar_e_obter_modelo():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("API Key não encontrada")
    
    genai.configure(api_key=api_key)
    
    # Lista modelos disponíveis para sua chave
    modelos_disponiveis = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos_disponiveis.append(m.name)
    except Exception as e:
        # Fallback se a listagem falhar
        return genai.GenerativeModel('gemini-pro')

    # Lógica de preferência: Flash > 1.5 > Pro
    modelo_escolhido = None
    
    # Tenta achar variações do Flash
    for m in modelos_disponiveis:
        if 'flash' in m.lower():
            modelo_escolhido = m
            break
    
    # Se não achar flash, tenta 1.5 pro
    if not modelo_escolhido:
        for m in modelos_disponiveis:
            if '1.5' in m and 'pro' in m:
                modelo_escolhido = m
                break
                
    # Se não achar nada específico, pega o primeiro disponível
    if not modelo_escolhido and modelos_disponiveis:
        modelo_escolhido = modelos_disponiveis[0]
    
    # Se a lista estiver vazia (raro), tenta o padrão antigo
    if not modelo_escolhido:
        modelo_escolhido = 'gemini-pro'
        
    print(f"🤖 Modelo selecionado automaticamente: {modelo_escolhido}")
    return genai.GenerativeModel(modelo_escolhido)


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
    try:
        
        try:
            model = configurar_e_obter_modelo()
        except Exception as e:
            return jsonify({'success': False, 'response': f"Erro na Configuração da IA: {str(e)}"}), 500

        
        if dados_globais['df'] is None:
            return jsonify({'success': False, 'response': '⚠️ Planilha não encontrada na memória. Faça upload novamente.'}), 400

        data = request.get_json() or {}
        query = data.get('query')
        if not query: return jsonify({'success': False, 'response': 'Pergunta vazia'}), 400

        # 3. Gera resposta
        df = dados_globais['df']
        amostra = df.head(5).to_string()
        prompt = f"""
        Atue como analista de dados.
        Contexto: Tabela com {len(df)} linhas. Colunas: {list(df.columns)}.
        Amostra dos dados:
        {amostra}
        
        Pergunta do usuário: {query}
        Responda de forma concisa baseada nos dados acima.
        """
        
        response = model.generate_content(prompt)
        return jsonify({'success': True, 'response': response.text})

    except Exception as e:
        erro_detalhado = traceback.format_exc()
        print(erro_detalhado)
        # Retorna o erro detalhado no chat para sabermos o que aconteceu
        return jsonify({'success': False, 'response': f"ERRO TÉCNICO:\n{str(e)}"}), 500
    
@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'): return jsonify({'error': 'Not found'}), 404
    return send_from_directory(STATIC_DIR, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
