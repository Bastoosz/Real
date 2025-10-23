// VARIÁVEIS GLOBAIS DE CONFIGURAÇÃO
// Detecta se está em produção (sem localhost) ou desenvolvimento
const isProduction = !window.location.hostname.includes('localhost') && 
                     !window.location.hostname.includes('127.0.0.1');

const BACKEND_URL = isProduction ? '' : 'http://127.0.0.1:5000';


// --- INICIALIZAÇÃO ---
// Esta função "wrapper" garante que o script só rode
// depois que todo o HTML for carregado.
window.addEventListener('DOMContentLoaded', () => {

    // --- TODO O SEU CÓDIGO VEM AQUI DENTRO ---

    let dadosCarregados = false;
    let uploadEmAndamento = false;

    // ELEMENTOS DO DOM
    const uploadInput = document.getElementById('spreadsheet-upload');
    const uploadStatus = document.getElementById('upload-status');
    const chatWindow = document.getElementById('chat-window');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button'); // Esta linha agora está segura
    const dataInfo = document.getElementById('data-info');
    const totalRows = document.getElementById('total-rows');
    const totalFiles = document.getElementById('total-files');
    const clearChatBtn = document.getElementById('clear-chat-btn');
    const inputHint = document.getElementById('input-hint');

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
            const response = await fetch(`${BACKEND_URL}/api/status`);
            const result = await response.json();
            
            if (result.dados_carregados) {
                dadosCarregados = true;
                userInput.disabled = false;
                sendButton.disabled = false;
                
                // Atualiza informações dos dados
                totalRows.textContent = result.total_linhas.toLocaleString('pt-BR');
                totalFiles.textContent = result.total_arquivos;
                dataInfo.style.display = 'block';
                
                uploadStatus.innerHTML = `✅ Sistema pronto! ${result.total_linhas.toLocaleString('pt-BR')} linhas carregadas.`;
                
                // Limpa chat e adiciona mensagem de boas-vindas
                chatWindow.innerHTML = '';
                addMessageToChat(
                    `👋 Olá! Estou pronto para responder suas perguntas sobre os dados de varejo tech.\n\n📊 Atualmente temos **${result.total_linhas.toLocaleString('pt-BR')} registros** em **${result.total_arquivos} arquivo(s)**.\n\nComo posso ajudar?`, 
                    'bot'
                );
            } else {
                uploadStatus.innerHTML = '⚠️ Nenhum dado carregado. Faça upload de uma planilha para começar.';
                userInput.disabled = true;
                sendButton.disabled = true;
            }
            
        } catch (error) {
            uploadStatus.innerHTML = '❌ Erro de conexão. Verifique se o servidor está rodando.';
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
        uploadStatus.innerHTML = `⏳ Processando '${file.name}'...`;
        
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${BACKEND_URL}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (result.success) {
                dadosCarregados = true;
                userInput.disabled = false;
                sendButton.disabled = false;
                
                // Atualiza stats
                totalRows.textContent = result.total_linhas.toLocaleString('pt-BR');
                totalFiles.textContent = result.total_arquivos;
                dataInfo.style.display = 'block';
                
                uploadStatus.innerHTML = `✅ ${result.message}`;
                
                addMessageToChat(
                    `📁 Nova planilha adicionada: **${result.filename}**\n\n${result.message}`, 
                    'bot'
                );
            } else {
                uploadStatus.innerHTML = `❌ Erro: ${result.message}`;
            }

        } catch (error) {
            uploadStatus.innerHTML = "❌ Erro de conexão com o servidor.";
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
            const response = await fetch(`${BACKEND_URL}/api/chat`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
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
    if (uploadInput) {
        uploadInput.addEventListener('change', handleFileUpload);
    }

    // Botão limpar chat
    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', async () => {
            if (confirm('Deseja limpar todo o histórico de conversas?')) {
                try {
                    await fetch(`${BACKEND_URL}/api/limpar_historico`, {
                        method: 'POST',
                        credentials: 'include'
                    });
                    
                    chatWindow.innerHTML = '';
                    addMessageToChat('🗑️ Histórico limpo! Como posso ajudar?', 'bot');
                } catch (error) {
                    console.error('Erro ao limpar histórico:', error);
                }
            }
        });
    }

    // Envio de mensagem
    const handleMessageSend = () => {
        const query = userInput.value.trim();
        if (query === "") return;

        addMessageToChat(query, 'user');
        userInput.value = "";
        
        sendQueryToBot(query);
    };

    if (sendButton) {
        sendButton.addEventListener('click', handleMessageSend);
    } else {
        console.error("FATAL: Elemento 'send-button' não foi encontrado!");
    }

    if (userInput) {
        userInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !sendButton.disabled) {
                event.preventDefault();
                handleMessageSend();
            }
        });

        // Esconde hint ao começar a digitar
        userInput.addEventListener('input', () => {
            if (inputHint) {
                if (userInput.value.length > 0) {
                    inputHint.style.opacity = '0';
                } else {
                    inputHint.style.opacity = '1';
                }
            }
        });
    } else {
        console.error("FATAL: Elemento 'user-input' não foi encontrado!");
    }

    // --- INICIALIZAÇÃO (que já estava no final) ---
    console.log('✅ TheoBot carregado');
    console.log('🔗 Backend:', BACKEND_URL || 'Mesma origem (produção)');
    
    // Verifica se há dados carregados
    verificarStatus();
});