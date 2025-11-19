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

# Carrega variáveis de ambiente (para desenvolvimento local)
load_dotenv()

# ==========================================
# CONFIGURAÇÕES DE DIRETÓRIO (FIX VERCEL)
# ==========================================
# Define o caminho absoluto para a pasta do projeto
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Define a pasta onde estão os arquivos do frontend (HTML/CSS/JS)
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Define a pasta de uploads
# Na Vercel, só podemos escrever na pasta '/tmp'. 
# Localmente, usamos a pasta 'uploads' na raiz.
if os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

# Cria a pasta de uploads se não existir
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# ==========================================
# INICIALIZAÇÃO DO FLASK
# ==========================================
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = secrets.token_hex(16)

# Configura CORS apenas para a API
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# ==========================================
# CONFIGURAÇÃO DO GEMINI
# ==========================================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    # Não damos raise error aqui para não quebrar o app inteiro se a chave falhar,
    # mas logamos o erro crítico.
    print("⚠️ GEMINI_API_KEY não encontrada! O chat não funcionará.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Seleção simplificada de modelo
        MODEL_NAME = 'gemini-1.5-flash'
        model = genai.GenerativeModel(MODEL_NAME)
        print(f"✅ Gemini configurado com modelo: {MODEL_NAME}")
    except Exception as e:
        print(f"❌ Erro ao configurar Gemini: {e}")

# ==========================================
# VARIÁVEIS GLOBAIS
# ==========================================
# Nota: Em Serverless (Vercel), variáveis globais podem ser resetadas
# entre requisições se a instância "dormir". Para um app simples ok,
# para produção robusta, idealmente usaria um banco de dados.
dados_globais = {
    'dataframe': None,
    'arquivos_carregados': [],
    'total_linhas': 0,
    'colunas': [],
    'data_carga': None
}

historicos = {}

# ==========================================
# FUNÇÕES AUXILIARES
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
        
        # Lógica de concatenação
        if dados_globais['dataframe'] is not None:
            # Verifica compatibilidade básica de colunas (opcional: pode ser mais flexível)
            colunas_existentes = set(dados_globais['colunas'])
            colunas_novas = set(df_novo.columns.tolist())
            
            # Concatena
            df_completo = pd.concat([dados_globais['dataframe'], df_novo], ignore_index=True)
            df_completo = df_completo.drop_duplicates()
        else:
            df_completo = df_novo
            
        # Atualiza globais
        dados_globais['dataframe'] = df_completo
        if filename not in dados_globais['arquivos_carregados']:
            dados_globais['arquivos_carregados'].append(filename)
        dados_globais['total_linhas'] = len(df_completo)
        dados_globais['colunas'] = df_completo.columns.tolist()
        dados_globais['data_carga'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return True, f"Adicionado com sucesso. Total linhas: {len(df_completo)}"
        
    except Exception as e:
        return False, f"Erro ao processar: {str(e)}"

def criar_contexto_ia(session_id=None):
    if dados_globais['dataframe'] is None:
        return "Nenhuma planilha carregada."
    
    df = dados_globais['dataframe']
    
    # Limita a amostra para economizar tokens
    amostra = df.head(5).to_string(index=False)
    
    contexto = f"""
    Você é um analista de dados.
    DADOS DISPONÍVEIS:
    - Linhas: {len(df)}
    - Colunas: {', '.join(df.columns.tolist())}
    
    AMOSTRA:
    {amostra}
    
    Responda com base APENAS nestes dados. Se não souber, diga que não há dados suficientes.
    """
    
    # Adiciona histórico curto
    if session_id and session_id in historicos:
        hist = historicos[session_id][-3:] # Últimas 3 mensagens apenas
        contexto += "\nHISTÓRICO RECENTE:\n"
        for h in hist:
            contexto += f"User: {h['pergunta']}\nBot: {h['resposta'][:100]}...\n"
            
    return contexto

# ==========================================
# ROTAS DA API
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
            return jsonify({
                'success': True, 
                'message': msg,
                'total_linhas': dados_globais['total_linhas']
            })
        else:
            return jsonify({'success': False, 'message': msg}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    if not dados_globais['dataframe'] is not None:
        return jsonify({'success': False, 'response': 'Por favor, faça upload de uma planilha primeiro.'}), 400

    data = request.get_json() or {}
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'success': False, 'response': 'Digite uma pergunta.'}), 400

    # Gestão de sessão
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(8)
    session_id = session['session_id']

    try:
        contexto = criar_contexto_ia(session_id)
        prompt = f"{contexto}\n\nPERGUNTA: {query}\nRESPOSTA:"
        
        response = model.generate_content(prompt)
        resposta_bot = response.text
        
        # Salva histórico
        if session_id not in historicos: historicos[session_id] = []
        historicos[session_id].append({'pergunta': query, 'resposta': resposta_bot})
        
        return jsonify({'success': True, 'response': resposta_bot, 'session_id': session_id})
        
    except Exception as e:
        return jsonify({'success': False, 'response': f"Erro na IA: {str(e)}"}), 500

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'online',
        'linhas': dados_globais['total_linhas'],
        'arquivos': dados_globais['arquivos_carregados']
    })

@app.route('/api/limpar_historico', methods=['POST'])
def limpar():
    if 'session_id' in session:
        historicos.pop(session['session_id'], None)
    return jsonify({'success': True})

# ==========================================
# ROTAS DO FRONTEND (SERVIR O SITE)
# ==========================================

@app.route('/')
def index():
    # Serve o index.html da pasta static configurada com caminho absoluto
    if not os.path.exists(os.path.join(STATIC_DIR, 'index.html')):
        return f"Erro: index.html não encontrado em {STATIC_DIR}", 404
    return send_from_directory(STATIC_DIR, 'index.html')

@app.errorhandler(404)
def not_found(e):
    # Se for rota de API, retorna JSON erro
    if request.path.startswith('/api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    
    # Se for qualquer outra coisa (ex: reload na página), serve o index.html
    return send_from_directory(STATIC_DIR, 'index.html')

# ==========================================
# EXECUÇÃO LOCAL
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Servidor rodando na porta {port}")
    print(f"📂 Pasta Static: {STATIC_DIR}")
    print(f"📂 Pasta Uploads: {UPLOAD_FOLDER}")
    app.run(host='0.0.0.0', port=port)