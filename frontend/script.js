// VARIÁVEIS GLOBAIS
// URL do seu backend Flask (padrão 5000)
const BACKEND_URL = 'http://127.0.0.1:5000'; 
let planilhaCarregada = false; // Flag para rastrear se a planilha foi processada no backend

// ELEMENTOS DO DOM
const uploadInput = document.getElementById('spreadsheet-upload');
const uploadStatus = document.getElementById('upload-status');
const chatWindow = document.getElementById('chat-window');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');

// --- FUNÇÕES DE UTENSILIDADE ---

/**
 * Adiciona uma mensagem ao chat.
 * @param {string} text - O conteúdo da mensagem.
 * @param {string} sender - 'user' ou 'bot'.
 */
function addMessageToChat(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${sender}-message`);
    
    // Adiciona o texto no formato de parágrafo
    messageDiv.innerHTML = `<p>${text}</p>`;
    
    chatWindow.appendChild(messageDiv);
    // Rola para a mensagem mais recente
    chatWindow.scrollTop = chatWindow.scrollHeight;
}


// --- LÓGICA DE UPLOAD (VIA API - SEM MENSAGEM NO CHAT) ---

/**
 * Envia o arquivo para o backend Flask e processa a resposta.
 * Remove todas as mensagens de chat para o usuário.
 * @param {Event} event - O evento de mudança do input file.
 */
async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Atualiza apenas o status da área de upload
    uploadStatus.textContent = `Enviando '${file.name}' para processamento...`;
    planilhaCarregada = false; 
    userInput.disabled = true;
    sendButton.disabled = true;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${BACKEND_URL}/upload`, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();

        if (result.success) {
            planilhaCarregada = true;
            userInput.disabled = false;
            sendButton.disabled = false;
            
            // APENAS ATUALIZA O STATUS DA ÁREA DE UPLOAD
            uploadStatus.textContent = `✅ Sucesso: ${result.filename} carregada. Comece a fazer perguntas!`;

        } else {
            uploadStatus.textContent = `❌ Erro no upload: ${result.message}`;
            // MANTÉM MENSAGEM DE ERRO APENAS NO STATUS (não no chat)
        }

    } catch (error) {
        uploadStatus.textContent = "❌ Erro de Conexão: O servidor backend não está ativo.";
        console.error("Erro de conexão com o backend:", error);
    }
}

// --- LÓGICA DO CHAT (VIA API) ---

/**
 * Envia a pergunta para a rota de chat do backend com o Gemini.
 * @param {string} query - A pergunta do usuário.
 */
async function sendQueryToBot(query) {
    if (!planilhaCarregada) {
        addMessageToChat("Por favor, carregue uma planilha antes de fazer perguntas.", 'bot');
        return;
    }

    userInput.disabled = true; // Desabilita enquanto espera a resposta
    sendButton.disabled = true;

    try {
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query }),
        });

        const result = await response.json();

        if (result.success) {
            addMessageToChat(result.response, 'bot');
        } else {
            // Se houver um erro, mas o servidor Flask respondeu
            addMessageToChat(`⚠️ Erro do Servidor: ${result.response || result.message}`, 'bot');
        }

    } catch (error) {
        // Erro de rede (servidor inativo)
        addMessageToChat("❌ Erro de Comunicação: Verifique se o servidor Flask está rodando na porta 5000.", 'bot');
        console.error("Erro na chamada de chat:", error);
    } finally {
        // Reativa os controles
        userInput.disabled = false;
        sendButton.disabled = false;
        userInput.focus(); 
    }
}

// --- EVENT LISTENERS ---

// 1. Upload da Planilha
uploadInput.addEventListener('change', handleFileUpload);

// 2. Envio da Mensagem
const handleMessageSend = () => {
    const query = userInput.value.trim();
    if (query === "") return;

    addMessageToChat(query, 'user');
    userInput.value = ""; // Limpa a caixa de entrada

    // Chama a função real de envio para o backend
    sendQueryToBot(query);
};

sendButton.addEventListener('click', handleMessageSend);

userInput.addEventListener('keydown', (event) => {
    // Permite o envio com Enter, desde que o botão não esteja desabilitado
    if (event.key === 'Enter' && !sendButton.disabled) {
        event.preventDefault(); // Evita quebra de linha no input
        handleMessageSend();
    }
});