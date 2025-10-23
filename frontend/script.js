// VARIÁVEIS GLOBAIS
const BACKEND_URL = 'http://127.0.0.1:5000'; 
let dadosCarregados = false;
let uploadEmAndamento = false;

// ELEMENTOS DO DOM
const uploadInput = document.getElementById('spreadsheet-upload');
const uploadStatus = document.getElementById('upload-status');
const chatWindow = document.getElementById('chat-window');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');

// --- FUNÇÕES DE UTILIDADE ---

/**
 * Adiciona uma mensagem ao chat
 */
function addMessageToChat(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${sender}-message`);
    messageDiv.innerHTML = `<p>${text}</p>`;
    
    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

/**
 * Mostra indicador de digitação
 */
function mostrarDigitando() {
    const typingDiv = document.createElement('div');
    typingDiv.classList.add('message', 'bot-message', 'typing-indicator');
    typingDiv.id = 'typing-indicator';
    typingDiv.innerHTML = '<p>Pensando<span class="dots">...</span></p>';
    
    chatWindow.appendChild(typingDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

/**
 * Remove indicador de digitação
 */
function removerDigitando() {
    const typingDiv = document.getElementById('typing-indicator');
    if (typingDiv) {
        typingDiv.remove();
    }
}

// --- VERIFICAR STATUS DO SISTEMA AO CARREGAR ---

/**
 * Verifica se há dados carregados no backend
 */
async function verificarStatus() {
    try {
        const response = await fetch(`${BACKEND_URL}/status`);
        const result = await response.json();
        
        if (result.dados_carregados) {
            dadosCarregados = true;
            userInput.disabled = false;
            sendButton.disabled = false;
            
            uploadStatus.innerHTML = `
                ✅ Sistema pronto!<br>
                📊 ${result.total_linhas.toLocaleString()} linhas em ${result.total_arquivos} arquivo(s)<br>
                📁 Carregados: ${result.arquivos.slice(0, 3).join(', ')}${result.arquivos.length > 3 ? '...' : ''}
            `;
            
            // Mensagem de boas-vindas
            addMessageToChat(
                `Olá! Estou pronto para responder suas perguntas sobre os dados de varejo tech. 
                Atualmente temos ${result.total_linhas.toLocaleString()} registros carregados. 
                Como posso ajudar?`, 
                'bot'
            );
        } else {
            uploadStatus.textContent = '⚠️ Nenhum dado carregado. Faça upload de uma planilha para começar.';
            userInput.disabled = true;
            sendButton.disabled = true;
        }
        
    } catch (error) {
        uploadStatus.textContent = '❌ Erro de conexão com o servidor.';
        console.error('Erro ao verificar status:', error);
        userInput.disabled = true;
        sendButton.disabled = true;
    }
}

// --- LÓGICA DE UPLOAD ---

/**
 * Adiciona nova planilha aos dados existentes
 */
async function handleFileUpload(event) {
    if (uploadEmAndamento) {
        console.log("⚠️ Upload já em andamento...");
        return;
    }

    const file = event.target.files[0];
    if (!file) return;

    uploadEmAndamento = true;
    uploadStatus.textContent = `Adicionando '${file.name}' aos dados...`;
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${BACKEND_URL}/upload`, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();

        if (result.success) {
            dadosCarregados = true;
            userInput.disabled = false;
            sendButton.disabled = false;
            
            uploadStatus.innerHTML = `
                ✅ ${result.message}<br>
                📊 Total: ${result.total_linhas.toLocaleString()} linhas em ${result.total_arquivos} arquivo(s)
            `;
            
            addMessageToChat(
                `Nova planilha adicionada: ${result.filename}. ${result.message}`, 
                'bot'
            );
        } else {
            uploadStatus.textContent = `❌ Erro: ${result.message}`;
        }

    } catch (error) {
        uploadStatus.textContent = "❌ Erro de conexão com o servidor.";
        console.error("Erro no upload:", error);
    } finally {
        uploadEmAndamento = false;
        event.target.value = '';
    }
}

// --- LÓGICA DO CHAT ---

/**
 * Envia pergunta para o bot
 */
async function sendQueryToBot(query) {
    if (!dadosCarregados) {
        addMessageToChat("Aguarde enquanto o sistema carrega os dados...", 'bot');
        return;
    }

    userInput.disabled = true;
    sendButton.disabled = true;
    
    mostrarDigitando();

    try {
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json'
            },
            credentials: 'include', // Importante para manter a sessão
            body: JSON.stringify({ query: query }),
        });

        const result = await response.json();
        
        removerDigitando();

        if (result.success) {
            addMessageToChat(result.response, 'bot');
        } else {
            addMessageToChat(`⚠️ Erro: ${result.response || result.message}`, 'bot');
        }

    } catch (error) {
        removerDigitando();
        addMessageToChat("❌ Erro de comunicação. Verifique se o servidor está rodando.", 'bot');
        console.error("Erro no chat:", error);
    } finally {
        userInput.disabled = false;
        sendButton.disabled = false;
        userInput.focus();
    }
}

// --- EVENT LISTENERS ---

// Upload de planilha
uploadInput.addEventListener('change', handleFileUpload);

// Envio de mensagem
const handleMessageSend = () => {
    const query = userInput.value.trim();
    if (query === "") return;

    addMessageToChat(query, 'user');
    userInput.value = "";
    
    sendQueryToBot(query);
};

sendButton.addEventListener('click', handleMessageSend);

userInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !sendButton.disabled) {
        event.preventDefault();
        handleMessageSend();
    }
});

// --- INICIALIZAÇÃO ---

// Verifica status ao carregar a página
window.addEventListener('DOMContentLoaded', () => {
    console.log('✅ Script carregado');
    console.log('🔗 Backend:', BACKEND_URL);
    
    // Verifica se há dados carregados
    verificarStatus();
});