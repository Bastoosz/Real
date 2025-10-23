import os
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import secrets

# Carrega variáveis de ambiente do .env
load_dotenv()

# --- ALTERAÇÃO 1: Configurar Pasta Estática ---
# Informamos ao Flask que nossos arquivos de frontend (index.html, script.js)
# estão na pasta 'public'.
# 'static_url_path' diz ao Flask para servi-los a partir da raiz ('/').
# Ex: Uma requisição para '/script.js' servirá o arquivo 'public/script.js'
app = Flask(__name__, static_folder='public', static_url_path='')
app.secret_key = secrets.token_hex(16)  # Necessário para sessões

# --- ALTERAÇÃO 2: Ajustar CORS ---
# Vamos aplicar o CORS apenas às rotas da API, que agora estão em '/api/*'
# Isso evita conflitos com as rotas que servem os arquivos.
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# Configurações
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

# Configuração do Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("⚠️ GEMINI_API_KEY não encontrada no arquivo .env")

print("\n" + "=" * 60)
print("🔑 TESTANDO CHAVE API DO GEMINI")
print("=" * 60)

try:
    genai.configure(api_key=GEMINI_API_KEY)
    
    print("✅ Chave API configurada com sucesso!")
    print("\n📋 Listando modelos disponíveis para sua chave:\n")
    
    modelos_disponiveis = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            nome_modelo = m.name.replace('models/', '')
            modelos_disponiveis.append(nome_modelo)
            print(f"   ✓ {nome_modelo}")
    
    if not modelos_disponiveis:
        print("   ⚠️ NENHUM MODELO DISPONÍVEL!")
        print("   Verifique se sua chave API está correta no arquivo .env")
        exit(1)
    
    # Tenta usar modelos na ordem de preferência (mais rápidos e com maior cota)
    if 'gemini-2.5-flash' in modelos_disponiveis:
        MODEL_NAME = 'gemini-2.5-flash'
    elif 'gemini-2.0-flash' in modelos_disponiveis:
        MODEL_NAME = 'gemini-2.0-flash'
    elif 'gemini-flash-latest' in modelos_disponiveis:
        MODEL_NAME = 'gemini-flash-latest'
    elif 'gemini-1.5-flash' in modelos_disponiveis:
        MODEL_NAME = 'gemini-1.5-flash'
    elif 'gemini-pro-latest' in modelos_disponiveis:
        MODEL_NAME = 'gemini-pro-latest'
    else:
        MODEL_NAME = modelos_disponiveis[0]
    
    print(f"\n🤖 Usando modelo: {MODEL_NAME}")
    model = genai.GenerativeModel(MODEL_NAME)
    
    # Teste rápido de geração
    print("\n🧪 Testando geração de conteúdo...")
    test_response = model.generate_content("Diga apenas 'OK'")
    print(f"✅ Resposta do modelo: {test_response.text.strip()}")
    print("=" * 60 + "\n")

except Exception as e:
    print(f"\n❌ ERRO AO CONFIGURAR GEMINI:")
    print(f"   {str(e)}")
    print("\nPossíveis causas:")
    print("   1. Chave API inválida ou expirada")
    print("   2. Sem conexão com a internet")
    print("   3. API do Google pode estar fora do ar")
    print("\nVerifique o arquivo .env e tente novamente.\n")
    print("=" * 60 + "\n")
    exit(1)

# Armazenamento global dos dados
dados_globais = {
    'dataframe': None,
    'arquivos_carregados': [],
    'total_linhas': 0,
    'colunas': [],
    'data_carga': None
}

# Histórico de conversas por sessão
historicos = {}


def carregar_planilhas_base():
    """
    Carrega automaticamente todas as planilhas da pasta uploads
    que seguem o padrão Varejo_Tech_*.csv
    """
    print("\n" + "=" * 60)
    print("📁 CARREGANDO PLANILHAS BASE")
    print("=" * 60)
    
    try:
        # Lista todos os arquivos CSV na pasta uploads
        arquivos = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.csv')]
        
        if not arquivos:
            print("⚠️ Nenhuma planilha encontrada na pasta uploads/")
            print("   O sistema funcionará apenas com uploads manuais.")
            return None
        
        print(f"📊 Encontrados {len(arquivos)} arquivo(s):\n")
        
        dataframes = []
        arquivos_carregados = []
        
        for arquivo in arquivos:
            try:
                filepath = os.path.join(UPLOAD_FOLDER, arquivo)
                df = pd.read_csv(filepath, encoding='utf-8')
                df = df.dropna(how='all')  # Remove linhas vazias
                
                dataframes.append(df)
                arquivos_carregados.append(arquivo)
                
                print(f"   ✓ {arquivo} - {len(df)} linhas")
                
            except Exception as e:
                print(f"   ✗ {arquivo} - ERRO: {str(e)}")
        
        if not dataframes:
            print("\n⚠️ Nenhuma planilha foi carregada com sucesso.")
            return None
        
        # Mescla todos os DataFrames
        df_completo = pd.concat(dataframes, ignore_index=True)
        
        # Remove duplicatas se houver
        df_completo = df_completo.drop_duplicates()
        
        print(f"\n✅ TOTAL: {len(df_completo)} linhas carregadas")
        print(f"📋 Colunas: {', '.join(df_completo.columns.tolist())}")
        print("=" * 60 + "\n")
        
        # Atualiza os dados globais
        dados_globais['dataframe'] = df_completo
        dados_globais['arquivos_carregados'] = arquivos_carregados
        dados_globais['total_linhas'] = len(df_completo)
        dados_globais['colunas'] = df_completo.columns.tolist()
        dados_globais['data_carga'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return df_completo
        
    except Exception as e:
        print(f"\n❌ Erro ao carregar planilhas base: {str(e)}\n")
        return None


def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def adicionar_nova_planilha(filepath, filename):
    """
    Adiciona uma nova planilha aos dados existentes
    """
    try:
        # Carrega a nova planilha baseado na extensão
        extensao = filename.lower().split('.')[-1]
        
        print(f"📄 Processando: {filename} (extensão: {extensao})")
        
        df_novo = None
        
        # Tenta carregar baseado na extensão
        if extensao == 'csv':
            df_novo = pd.read_csv(filepath, encoding='utf-8')
        elif extensao == 'xlsx':
            try:
                df_novo = pd.read_excel(filepath, engine='openpyxl')
            except Exception as e:
                print(f"⚠️ Falha ao ler como XLSX, tentando como CSV: {str(e)}")
                # Tenta ler como CSV caso o arquivo esteja com extensão errada
                df_novo = pd.read_csv(filepath, encoding='utf-8')
        elif extensao == 'xls':
            df_novo = pd.read_excel(filepath, engine='xlrd')
        else:
            return False, f"Formato não suportado: .{extensao}. Use CSV ou XLSX."
        
        if df_novo is None:
            return False, "Não foi possível processar o arquivo."
        
        df_novo = df_novo.dropna(how='all')
        
        # Verifica se as colunas são compatíveis
        if dados_globais['dataframe'] is not None:
            colunas_existentes = set(dados_globais['colunas'])
            colunas_novas = set(df_novo.columns.tolist())
            
            if colunas_existentes != colunas_novas:
                diferenca = colunas_novas.symmetric_difference(colunas_existentes)
                return False, f"Colunas incompatíveis. Diferenças: {', '.join(diferenca)}"
            
            # Mescla com os dados existentes
            df_completo = pd.concat([dados_globais['dataframe'], df_novo], ignore_index=True)
            df_completo = df_completo.drop_duplicates()
        else:
            # Primeira planilha
            df_completo = df_novo
        
        # Atualiza os dados globais
        dados_globais['dataframe'] = df_completo
        dados_globais['arquivos_carregados'].append(filename)
        dados_globais['total_linhas'] = len(df_completo)
        dados_globais['colunas'] = df_completo.columns.tolist()
        
        return True, f"{len(df_novo)} novas linhas adicionadas. Total: {len(df_completo)} linhas."
        
    except Exception as e:
        return False, f"Erro ao processar planilha: {str(e)}"


def criar_contexto_ia(incluir_historico=True, session_id=None):
    """
    Cria o contexto para o Gemini com os dados e histórico
    """
    if dados_globais['dataframe'] is None:
        return "Nenhuma planilha carregada no momento."
    
    df = dados_globais['dataframe']
    
    contexto = f"""
Você é um assistente de análise de dados de varejo tech. Abaixo estão as informações da base de dados:

DADOS CARREGADOS:
- Total de linhas: {len(df)}
- Total de colunas: {len(df.columns)}
- Arquivos: {', '.join(dados_globais['arquivos_carregados'])}
- Data de carga: {dados_globais['data_carga']}

COLUNAS DISPONÍVEIS:
{', '.join(df.columns.tolist())}

TIPOS DE DADOS:
{df.dtypes.to_string()}

ESTATÍSTICAS DESCRITIVAS (colunas numéricas):
{df.describe().to_string() if not df.select_dtypes(include='number').empty else 'Nenhuma coluna numérica'}

AMOSTRA DOS DADOS (primeiras 10 linhas):
{df.head(10).to_string(index=False)}
"""

    # Adiciona histórico da conversa se disponível
    if incluir_historico and session_id and session_id in historicos:
        historico = historicos[session_id]
        if historico:
            contexto += "\n\nHISTÓRICO DA CONVERSA:\n"
            for i, msg in enumerate(historico[-5:], 1):  # Últimas 5 mensagens
                contexto += f"{i}. USER: {msg['pergunta']}\n"
                contexto += f"   BOT: {msg['resposta'][:200]}...\n"  # Resumo

    contexto += """

INSTRUÇÕES:
- Responda perguntas sobre os dados de forma clara e objetiva
- Use o histórico da conversa para manter contexto
- Quando necessário, realize cálculos, filtragens ou agregações
- Formate números grandes com separadores (ex: 1.234.567)
- Se a pergunta não puder ser respondida com os dados, informe educadamente
- Seja preciso e base suas respostas EXCLUSIVAMENTE nos dados fornecidos
"""
    
    return contexto


def salvar_no_historico(session_id, pergunta, resposta):
    """
    Salva uma interação no histórico da sessão
    """
    if session_id not in historicos:
        historicos[session_id] = []
    
    historicos[session_id].append({
        'timestamp': datetime.now().isoformat(),
        'pergunta': pergunta,
        'resposta': resposta
    })
    
    # Limita o histórico a 50 mensagens por sessão
    if len(historicos[session_id]) > 50:
        historicos[session_id] = historicos[session_id][-50:]


# --- ALTERAÇÃO 3: Adicionar prefixo /api ---
# Todas as suas rotas de API agora têm o prefixo /api/
# para corresponder ao que o script.js está chamando.

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """
    Adiciona uma nova planilha aos dados existentes
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': 'Nenhum arquivo foi enviado'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'Nenhum arquivo selecionado'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'message': f'Formato não suportado. Use: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400
        
        # Salva o arquivo
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Adiciona aos dados existentes
        sucesso, mensagem = adicionar_nova_planilha(filepath, filename)
        
        if sucesso:
            return jsonify({
                'success': True,
                'filename': filename,
                'message': mensagem,
                'total_linhas': dados_globais['total_linhas'],
                'total_arquivos': len(dados_globais['arquivos_carregados'])
            })
        else:
            return jsonify({
                'success': False,
                'message': mensagem
            }), 400
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Recebe uma pergunta e retorna resposta do Gemini com contexto e histórico
    """
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({
                'success': False,
                'response': 'Por favor, envie uma pergunta válida.'
            }), 400
        
        if dados_globais['dataframe'] is None:
            return jsonify({
                'success': False,
                'response': 'Nenhuma planilha carregada no sistema.'
            }), 400
        
        # Obtém ou cria session_id
        if 'session_id' not in session:
            session['session_id'] = secrets.token_hex(8)
        
        session_id = session['session_id']
        
        # Monta o prompt com contexto e histórico
        contexto = criar_contexto_ia(incluir_historico=True, session_id=session_id)
        prompt = f"{contexto}\n\nPERGUNTA DO USUÁRIO:\n{query}\n\nRESPOSTA:"
        
        # Chama o Gemini
        print(f"🤖 [{session_id[:8]}] Processando: {query}")
        response = model.generate_content(prompt)
        resposta_bot = response.text
        print(f"✅ Resposta gerada")
        
        # Salva no histórico
        salvar_no_historico(session_id, query, resposta_bot)
        
        return jsonify({
            'success': True,
            'response': resposta_bot,
            'session_id': session_id
        })
    
    except Exception as e:
        print(f"❌ Erro no chat: {str(e)}")
        return jsonify({
            'success': False,
            'response': f'Erro ao processar pergunta: {str(e)}'
        }), 500


@app.route('/api/historico', methods=['GET'])
def obter_historico():
    """
    Retorna o histórico de conversas da sessão atual
    """
    if 'session_id' not in session:
        return jsonify({
            'success': True,
            'historico': []
        })
    
    session_id = session['session_id']
    historico = historicos.get(session_id, [])
    
    return jsonify({
        'success': True,
        'historico': historico,
        'total': len(historico)
    })


@app.route('/api/limpar_historico', methods=['POST'])
def limpar_historico():
    """
    Limpa o histórico da sessão atual
    """
    if 'session_id' in session:
        session_id = session['session_id']
        if session_id in historicos:
            del historicos[session_id]
    
    return jsonify({
        'success': True,
        'message': 'Histórico limpo com sucesso'
    })


# --- ALTERAÇÃO 4: Mover rota raiz original ---
# A sua rota '/' antiga (que mostrava o JSON) foi movida para '/api'
@app.route('/api')
def api_home():
    """
    Página inicial da API - confirma que o backend está online
    """
    return jsonify({
        'status': 'online',
        'message': '🤖 TheoBot API está rodando!',
        'version': '1.0',
        'endpoints': {
            '/api/status': 'GET - Verifica status do sistema',
            '/api/upload': 'POST - Faz upload de planilhas',
            '/api/chat': 'POST - Envia mensagens para o bot',
            '/api/historico': 'GET - Obtém histórico de conversas',
            '/api/limpar_historico': 'POST - Limpa o histórico'
        }
    })


@app.route('/api/status', methods=['GET'])
def status():
    """
    Retorna informações sobre o sistema
    """
    return jsonify({
        'status': 'online',
        'modelo': MODEL_NAME,
        'dados_carregados': dados_globais['dataframe'] is not None,
        'total_linhas': dados_globais['total_linhas'],
        'total_arquivos': len(dados_globais['arquivos_carregados']),
        'arquivos': dados_globais['arquivos_carregados'],
        'colunas': dados_globais['colunas'],
        'data_carga': dados_globais['data_carga']
    })


# --- ALTERAÇÃO 5: Servir o Aplicativo Frontend ---
# Estas rotas garantem que o seu site (index.html) seja servido.

@app.route('/')
def serve_app():
    """
    Serve a página principal (index.html) da pasta 'public'
    """
    return send_from_directory(app.static_folder, 'index.html')


@app.errorhandler(404)
def not_found(e):
    """
    Se uma rota não for encontrada (404), verifica:
    1. Se for um 404 da API, retorna JSON de erro.
    2. Se for um 404 do site (ex: usuário recarregou a página),
       serve o index.html para o frontend carregar.
    """
    # Se o caminho não for da API, serve o index.html
    if not request.path.startswith('/api/'):
        return send_from_directory(app.static_folder, 'index.html')
    
    # É uma rota da API que não existe
    return jsonify({'success': False, 'message': 'Endpoint da API não encontrado'}), 404


if __name__ == '__main__':
    # Carrega as planilhas base automaticamente
    carregar_planilhas_base()
    
    print("=" * 60)
    print("🚀 SERVIDOR FLASK INICIADO (MODO HÍBRIDO: API + FRONTEND)")
    print("=" * 60)
    print("📊 Backend de Chat com Planilhas + Gemini AI")
    print(f"🤖 Modelo ativo: {MODEL_NAME}")
    print(f"📁 Total de linhas: {dados_globais['total_linhas']}")
    print(f"📋 Arquivos carregados: {len(dados_globais['arquivos_carregados'])}")
    print(f"🔧 Porta: {os.getenv('PORT', 5000)}")
    print("=" * 60 + "\n")
    
    # Detecta se está em produção (Render) ou desenvolvimento
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
