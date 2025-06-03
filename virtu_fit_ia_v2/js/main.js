// === JavaScript v3.14 - Feedback por Dia (Salvar REAL) e Refazer Dia (Integrado) ===

// --- Variáveis Globais ---
let alunosCadastrados = [];
let alunoSelecionadoId = null;
let alunoSelecionadoNome = "";
let token = null;
let usernameLogado = null;
const API_BASE_URL = "https://evolua-fit-api.onrender.com"; // CONFIRME A PORTA
let planoAtualCache = null;
let historicoMedidasCompleto = []; // Para guardar os dados ordenados e usar no modal
let feedbackDiaAtual = {}; // Objeto para guardar o estado do feedback por dia

// --- Funções Auxiliares ---
function setMsg(element, text, type = "info", timeout = 0) {
    if(!element) return;
    element.innerText = text;
    let alertType = type === 'error' ? 'danger' : (type === 'success' ? 'success' : (type === 'warning' ? 'warning' : 'info'));
    element.className = `msg alert alert-${alertType}`;
    element.style.display = text ? 'block' : 'none';
    if (timeout > 0) { setTimeout(() => { if (element && element.innerText === text) { element.style.display = 'none'; element.className = 'msg'; } }, timeout); }
}
function formatDate(dateString) {
    if (!dateString) return '?'; try { let isoString = dateString; if (typeof dateString === 'string') { if (dateString.includes(' ') && !dateString.includes('T')) { isoString = dateString.replace(' ', 'T'); } if (!isoString.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(isoString)) { isoString += 'Z';} } else { isoString = new Date(dateString).toISOString(); } const d = new Date(isoString); if (isNaN(d.getTime())) { return '?'; } const optsDate = { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' }; const optsTime = { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }; let fmtDate = new Intl.DateTimeFormat('pt-BR', optsDate).format(d); let fmtTime = ''; if (d.getUTCHours() !== 0 || d.getUTCMinutes() !== 0 || d.getUTCSeconds() !== 0 || d.getUTCMilliseconds() !== 0) { fmtTime = new Intl.DateTimeFormat('pt-BR', optsTime).format(d); } return fmtTime ? `${fmtDate} ${fmtTime}` : fmtDate; } catch(e) { return '?'; }
}

// --- Gerenciamento de Token e Usuário ---
function storeToken(newToken) { token = newToken; localStorage.setItem('virtufit_token', newToken); }
function getToken() { if (!token) { token = localStorage.getItem('virtufit_token'); } return token; }
function clearToken() { token = null; usernameLogado = null; localStorage.removeItem('virtufit_token'); localStorage.removeItem('virtufit_username'); }
function storeUsername(username) { usernameLogado = username; localStorage.setItem('virtufit_username', username); }
function getUsername() { if (!usernameLogado) { usernameLogado = localStorage.getItem('virtufit_username'); } return usernameLogado; }

// --- Autenticação ---
async function login() {
    const u = document.getElementById("loginUsername")?.value; const p = document.getElementById("loginPassword")?.value; const msg = document.getElementById("loginMsg"); if (!u || !p || !msg) { if(msg) setMsg(msg, "Campos de login não encontrados.", "error"); return; } setMsg(msg, "Verificando...", "info"); const fd = new FormData(); fd.append("username", u); fd.append("password", p); try { const r = await fetch(`${API_BASE_URL}/token`, { method: "POST", body: new URLSearchParams(fd) }); if (r.ok) { const d = await r.json(); if (d.access_token) { storeToken(d.access_token); storeUsername(u); setMsg(msg, "Login bem-sucedido!", "success", 1500); setTimeout(showMainApp, 500); } else { setMsg(msg, "Erro: Token não recebido.", "error"); } } else { let err = "Login falhou."; try { const ed = await r.json(); err = ed.detail || err; } catch (e) {} setMsg(msg, err, "error"); clearToken(); } } catch (e) { setMsg(msg, "Erro de comunicação.", "error"); clearToken(); }
}
function logout() {
    clearToken();
    document.getElementById('mainAppDiv').style.display = 'none';
    document.getElementById('authDiv').style.display = 'block';
    alunosCadastrados = [];
    alunoSelecionadoId = null;
    alunoSelecionadoNome = "";
    planoAtualCache = null;
    historicoMedidasCompleto = [];
    feedbackDiaAtual = {}; // <<< Limpa estado do feedback por dia

    const elInfo = document.getElementById("alunoSelecionadoInfo"); if(elInfo) { elInfo.innerHTML = 'Nenhum aluno selecionado.'; elInfo.className = 'alert alert-secondary mt-3 text-center'; }
    const botoesContainer = document.getElementById("containerBotoesAcao"); if (botoesContainer) botoesContainer.style.display = 'none';
    const btnVerDados = document.getElementById("historicoHeaderActions"); if(btnVerDados) btnVerDados.style.display = 'none';
    const elBusca = document.getElementById("alunoNomeBusca"); if(elBusca) elBusca.value = '';
    const rDiv = document.getElementById("buscaResultados"); if(rDiv) rDiv.innerHTML = "";

    const elPlanoTabela = document.getElementById("tabelaPlanoContainer"); if(elPlanoTabela) elPlanoTabela.innerHTML='<div class="alert alert-info text-center">Gere um plano ou veja histórico.</div>';
    const elNomeAluno = document.getElementById("nomeAlunoParaImpressao"); if (elNomeAluno) elNomeAluno.innerHTML = "";
    const elObsGerais = document.getElementById("observacoesGeraisContainer"); if (elObsGerais) elObsGerais.innerHTML = "";
    const titPlano = document.getElementById("tituloPlanoGerado"); if (titPlano) titPlano.innerText = "Plano Atual";
    const btnP = document.getElementById("botaoImprimir"); if(btnP) btnP.style.display='none';
    const btnR = document.getElementById("botaoRegerar"); if(btnR) btnR.style.display='none';

    const feedbackSectionAntiga = document.getElementById('feedbackPlanoSection'); if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
    const feedbackSectionNova = document.getElementById('feedbackGrupoSection'); if(feedbackSectionNova) feedbackSectionNova.remove();
    const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer'); if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

    const elHistP = document.getElementById('historicoPlanos'); if(elHistP) elHistP.innerHTML='<div class="historico-vazio">Selecione um aluno.</div>';
    const elHistM = document.getElementById('historicoMedidas'); if(elHistM) elHistM.innerHTML='<div class="historico-vazio">Selecione um aluno.</div>';
    const histInfo = document.getElementById("historicoAlunoInfo"); if(histInfo) histInfo.innerHTML = `Selecione um aluno`;

    const loginTab = document.getElementById('login-tab'); if(loginTab) bootstrap.Tab.getOrCreateInstance(loginTab).show();
    const lu = document.getElementById('loginUsername'); if(lu) lu.value = '';
    const lp = document.getElementById('loginPassword'); if(lp) lp.value = '';
}

// --- App Principal e Fetch Autenticado ---
async function showMainApp() {
    document.getElementById('authDiv').style.display = 'none'; document.getElementById('mainAppDiv').style.display = 'block'; const userInfoDiv = document.getElementById('userInfo'); const user = getUsername(); if (userInfoDiv && user) { userInfoDiv.innerHTML = `Logado como: <strong>${user}</strong> <button class="btn btn-sm btn-outline-secondary" onclick="logout()">Sair</button>`; } else if (userInfoDiv) { userInfoDiv.innerHTML = ''; } try { await carregarListaCompletaAlunos(); } catch (e) { console.error("Falha carregar lista inicial alunos:", e); } const firstTabEl = document.getElementById('gerar-tab'); if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();
}
async function fetchAutenticado(url, options = {}) {
    const currentToken = getToken();
    if (!currentToken) { logout(); throw new Error("Não autenticado"); }
    const defaultHeaders = { 'Authorization': `Bearer ${currentToken}` };
    if (options.body && !options.headers?.['Content-Type'] && !(options.body instanceof FormData)) { defaultHeaders['Content-Type'] = 'application/json'; }
    options.headers = { ...defaultHeaders, ...options.headers }; options.credentials = options.credentials || 'same-origin';
    const response = await fetch(url, options); if (response.status === 401) { logout(); throw new Error("Sessão expirada ou inválida"); } return response;
}

// --- CRUD Aluno ---
async function cadastrarAluno() {
    const msg = document.getElementById("cadastroMsg"); setMsg(msg, "Salvando dados do aluno...", "info");
    const nome = document.getElementById("nome").value, sexo = document.getElementById("sexo").value, idade = document.getElementById("idade").value, nivel = document.getElementById("nivel").value;
    const medidas = {}; const camposMedidasCadastro = ['cad_altura_cm','cad_peso_kg','cad_circ_ombros_cm','cad_circ_peito_cm','cad_circ_cintura_cm','cad_circ_quadril_cm','cad_circ_biceps_d_relaxado_cm','cad_circ_biceps_e_relaxado_cm','cad_circ_biceps_d_contraido_cm','cad_circ_biceps_e_contraido_cm','cad_circ_antebraco_d_cm','cad_circ_antebraco_e_cm','cad_circ_coxa_d_cm','cad_circ_coxa_e_cm','cad_circ_panturrilha_d_cm','cad_circ_panturrilha_e_cm','cad_dc_triceps_mm','cad_dc_subescapular_mm','cad_dc_peitoral_axilar_mm','cad_dc_suprailiaca_mm','cad_dc_abdominal_mm','cad_dc_coxa_mm','cad_dc_panturrilha_mm'];
    camposMedidasCadastro.forEach(id => { const el = document.getElementById(id); const v = el ? el.value.trim() : null; if(v) { const n = parseFloat(v); if(!isNaN(n) && n >= 0) { const backendKey = el.name; if(backendKey) medidas[backendKey] = n; } } });
    const objetivos = document.getElementById("objetivos").value, histLesoes = document.getElementById("historico_lesoes").value, foco = document.getElementById("foco_treino").value;
    if (!nome || !sexo || !idade || !nivel || !foco) { setMsg(msg, "Preencha os campos obrigatórios: Nome, Sexo, Idade, Nível, Foco.", "warning"); return; }
    let nivelFormatado = nivel; if (nivel === 'Intermediario') nivelFormatado = 'Intermediário'; if (nivel === 'Avancado') nivelFormatado = 'Avançado';
    const alunoData = { nome: nome, sexo: sexo, idade: parseInt(idade), nivel: nivelFormatado, medidas: medidas, objetivos: objetivos, historico_lesoes: histLesoes || "", foco_treino: foco || "" };
    try {
        const r = await fetchAutenticado(`${API_BASE_URL}/alunos`, { method: "POST", body: JSON.stringify(alunoData), headers: {'Content-Type':'application/json'} }); let data = {}; try { data = await r.json(); } catch (jsonError) { try { const textError = await r.text(); data = { detail: textError || `Erro ${r.status}` }; } catch (textErr) { data = { detail: `Erro ${r.status}` }; } }
        if (r.ok) { setMsg(msg, data.message || "Aluno cadastrado com sucesso!", "success", 3000); alunosCadastrados = []; document.getElementById('formCadastroAluno').reset(); const trigger = document.getElementById('gerar-tab'); if (trigger) bootstrap.Tab.getOrCreateInstance(trigger).show(); } else { let errorDetail = "Erro ao cadastrar."; if (data?.detail) { if (Array.isArray(data.detail)) { errorDetail = data.detail.map(err => `${err.loc?.[1] || 'Campo'}: ${err.msg}`).join(' | '); } else { errorDetail = String(data.detail); } } else { errorDetail = `Erro ${r.status}.`; } setMsg(msg, errorDetail, "error"); }
    } catch (e) { if (e.message !== "Não autenticado" && e.message !== "Sessão expirada ou inválida") { setMsg(msg, "Erro de comunicação ao cadastrar.", "error"); } }
}
async function carregarListaCompletaAlunos() {
     if (alunosCadastrados && alunosCadastrados.length > 0) { return; } console.log("Carregando lista completa de alunos do backend..."); const msgDiv = document.getElementById("gerarTreinoMsg");
     try { const r = await fetchAutenticado(`${API_BASE_URL}/alunos`); if (r.ok) { const d = await r.json(); alunosCadastrados = Array.isArray(d) ? d : []; console.log(`Lista de ${alunosCadastrados.length} alunos carregada.`); if(msgDiv && msgDiv.innerText.includes("Carregando lista")) setMsg(msgDiv,""); } else { alunosCadastrados = []; const data = await r.json().catch(() => ({ detail: `Erro HTTP ${r.status}` })); console.error("Falha ao carregar lista de alunos:", data); if(msgDiv) setMsg(msgDiv, data.detail || `Erro ao carregar alunos (${r.status})`, "error", 5000); }
     } catch (e) { if (e.message !== "Não autenticado" && e.message !== "Sessão expirada ou inválida") { console.error("Erro de conexão ao carregar alunos:", e); if(msgDiv) setMsg(msgDiv, "Erro de conexão ao buscar alunos.", "error", 5000); } alunosCadastrados = []; }
}

// --- Busca e Seleção de Aluno ---
async function buscarAlunoPorNome() {
     const termo = document.getElementById("alunoNomeBusca")?.value.trim().toLowerCase(); const rDiv = document.getElementById("buscaResultados"); const msgDiv = document.getElementById("gerarTreinoMsg"); const infoEl = document.getElementById("alunoSelecionadoInfo"); const botoesContainer = document.getElementById("containerBotoesAcao"); const btnVerDados = document.getElementById("historicoHeaderActions"); if(!rDiv || !msgDiv || !infoEl || !botoesContainer || !btnVerDados){ return; } rDiv.innerHTML = ""; setMsg(msgDiv, "", null); if (alunoSelecionadoId) { infoEl.className = 'alert alert-secondary mt-3 text-center'; infoEl.innerHTML='Nenhum aluno selecionado.'; botoesContainer.style.display = 'none'; btnVerDados.style.display = 'none'; alunoSelecionadoId = null; alunoSelecionadoNome = ""; planoAtualCache = null; historicoMedidasCompleto = [];
     feedbackDiaAtual = {}; // <<< Limpa estado do feedback por dia

     const elPlanoTabela = document.getElementById("tabelaPlanoContainer"); if(elPlanoTabela) elPlanoTabela.innerHTML='<div class="alert alert-info text-center">Gere um plano ou veja histórico.</div>';
     const elNomeAluno = document.getElementById("nomeAlunoParaImpressao"); if (elNomeAluno) elNomeAluno.innerHTML = "";
     const elObsGerais = document.getElementById("observacoesGeraisContainer"); if (elObsGerais) elObsGerais.innerHTML = "";
     const titPlano = document.getElementById("tituloPlanoGerado"); if (titPlano) titPlano.innerText = "Plano Atual";
     const btnP = document.getElementById("botaoImprimir"); if(btnP) btnP.style.display='none';
     const btnR = document.getElementById("botaoRegerar"); if(btnR) btnR.style.display='none';

     const feedbackSectionAntiga = document.getElementById('feedbackPlanoSection'); if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
     const feedbackSectionNova = document.getElementById('feedbackGrupoSection'); if(feedbackSectionNova) feedbackSectionNova.remove();
     const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer'); if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

     const elHistP = document.getElementById('historicoPlanos'); if(elHistP) elHistP.innerHTML='<div class="historico-vazio">Selecione um aluno.</div>'; const elHistM = document.getElementById('historicoMedidas'); if(elHistM) elHistM.innerHTML='<div class="historico-vazio">Selecione um aluno.</div>'; const histInfo = document.getElementById("historicoAlunoInfo"); if(histInfo) histInfo.innerHTML = `Selecione um aluno`; } if (!termo) { setMsg(msgDiv, "Digite parte do nome para buscar.", "warning", 3000); return; } if (!alunosCadastrados || alunosCadastrados.length === 0) { setMsg(msgDiv, "Carregando lista de alunos...", "info"); await carregarListaCompletaAlunos(); if (alunosCadastrados.length === 0) { setMsg(msgDiv, "Nenhum aluno cadastrado ou falha ao carregar.", "warning", 4000); return; } setMsg(msgDiv, "", null); } const encontrados = alunosCadastrados.filter(a => a?.nome?.toLowerCase().includes(termo)); if (encontrados.length === 0) { rDiv.innerHTML = "<div class='alert alert-light text-center p-2 small'>Nenhum aluno encontrado com esse nome.</div>"; } else { rDiv.innerHTML = ""; encontrados.forEach(aluno => { if(!aluno?.id || !aluno.nome) { console.warn("Aluno inválido na lista:", aluno); return; } const itemDiv = document.createElement("div"); itemDiv.className = "resultado-item"; itemDiv.innerHTML = `<span>${aluno.nome} <small class='text-muted'>(ID: ${aluno.id})</small></span><button class="btn btn-sm btn-outline-success py-1 px-2 ms-2">Selecionar</button>`; itemDiv.addEventListener('click', (e) => { e.stopPropagation(); selecionarAluno(aluno.id, aluno.nome); }); rDiv.appendChild(itemDiv); }); }
}
function selecionarAluno(id, nome) {
    console.log(`Aluno selecionado: ID ${id}, Nome: ${nome}`);
    alunoSelecionadoId = id; alunoSelecionadoNome = nome; planoAtualCache = null; historicoMedidasCompleto = [];
    feedbackDiaAtual = {}; // <<< Limpa estado do feedback por dia

    const infoEl = document.getElementById("alunoSelecionadoInfo"); const botoesContainer = document.getElementById("containerBotoesAcao"); const btnVerDados = document.getElementById("historicoHeaderActions"); if(infoEl) { infoEl.innerHTML = `Aluno Selecionado: <strong>${nome}</strong> <small class='text-muted'>(ID: ${id})</small>`; infoEl.className = 'alert alert-success mt-3 text-center'; } if (botoesContainer) { botoesContainer.style.display = 'flex'; } const resDiv = document.getElementById("buscaResultados"); if(resDiv) resDiv.innerHTML = ""; const bInput = document.getElementById("alunoNomeBusca"); if(bInput) bInput.value = ""; const pContTabela = document.getElementById("tabelaPlanoContainer"); if(pContTabela) pContTabela.innerHTML='<div class="alert alert-info text-center">Gere um novo plano ou veja o histórico.</div>'; const titP = document.getElementById("tituloPlanoGerado"); if(titP) titP.innerText = "Plano Atual"; const btnI = document.getElementById("botaoImprimir"); if(btnI) btnI.style.display='none'; const btnR = document.getElementById("botaoRegerar"); if(btnR) btnR.style.display='none';

    const feedbackSectionAntiga = document.getElementById('feedbackPlanoSection'); if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
    const feedbackSectionNova = document.getElementById('feedbackGrupoSection'); if(feedbackSectionNova) feedbackSectionNova.remove();
    const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer'); if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

    const elNomeAluno = document.getElementById("nomeAlunoParaImpressao"); if (elNomeAluno) elNomeAluno.innerHTML = ""; const elObsGerais = document.getElementById("observacoesGeraisContainer"); if (elObsGerais) elObsGerais.innerHTML = ""; const hInfo = document.getElementById("historicoAlunoInfo"); if(hInfo) hInfo.innerHTML = `Histórico: <strong>${nome} (ID: ${id})</strong>`; const histP = document.getElementById('historicoPlanos'); if(histP) histP.innerHTML='<div class="historico-vazio">Carregando...</div>'; const histM = document.getElementById('historicoMedidas'); if(histM) histM.innerHTML='<div class="historico-vazio">Carregando...</div>'; const activeTab = document.querySelector('#mainTabs .nav-link.active'); if (activeTab) { const targetPaneId = activeTab.getAttribute('data-bs-target'); if (targetPaneId === '#historico') { carregarHistoricoAluno(); } else if (targetPaneId === '#plano') { carregarUltimoPlanoAluno(); } }
}

// --- Geração de Plano ---
async function gerarPlanoSemanal() {
    const msg = document.getElementById("gerarTreinoMsg"); const contTabela = document.getElementById("tabelaPlanoContainer"); const nomeAlunoDiv = document.getElementById("nomeAlunoParaImpressao"); const obsContainer = document.getElementById("observacoesGeraisContainer"); const btnP = document.getElementById("botaoImprimir"); const btnR = document.getElementById("botaoRegerar"); const titP = document.getElementById("tituloPlanoGerado");
    feedbackDiaAtual = {}; // <<< Limpa estado do feedback por dia
    console.log("Iniciando gerarPlanoSemanal para aluno:", alunoSelecionadoId);
    if(!msg||!contTabela||!btnP||!btnR||!titP||!nomeAlunoDiv||!obsContainer) { console.error("Erro: Um ou mais elementos do DOM não foram encontrados em gerarPlanoSemanal."); return; } setMsg(msg,"",null); contTabela.innerHTML='<div class="text-center p-5"><div class="loader"></div> Gerando plano com IA... Por favor, aguarde.</div>'; nomeAlunoDiv.innerHTML = ""; obsContainer.innerHTML = ""; btnP.style.display='none'; btnR.style.display='none'; titP.innerText = "Gerando Plano...";
    const feedbackSectionAntiga = document.getElementById('feedbackPlanoSection'); if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
    const feedbackSectionNova = document.getElementById('feedbackGrupoSection'); if(feedbackSectionNova) feedbackSectionNova.remove();
    const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer'); if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

    if (!alunoSelecionadoId) { setMsg(msg, "Selecione um aluno antes de gerar.", "warning"); contTabela.innerHTML = '<div class="alert alert-info text-center">Selecione um aluno na aba anterior.</div>'; titP.innerText = "Plano Atual"; return; } setMsg(msg, `Gerando plano para ${alunoSelecionadoNome}...`, "info");
    try { const url = `${API_BASE_URL}/gerar_treino_ia/${alunoSelecionadoId}`; console.log("Chamando API:", url); const resp = await fetchAutenticado(url, { method: "POST" }); console.log("API respondeu com status:", resp.status); let data; try { data = await resp.json(); console.log("Dados recebidos da API (JSON):", data); } catch (e) { console.error("Erro ao fazer parse do JSON da API:", e); const txt = await resp.text().catch(() => 'Erro ao ler texto da resposta'); setMsg(msg, `Erro ${resp.status} servidor (resposta não é JSON válido).`, "error"); contTabela.innerHTML = `<div class="alert alert-danger">Erro ao processar resposta do servidor: ${txt || 'Resposta inválida.'}</div>`; titP.innerText = "Erro ao Gerar"; return; }
        if (resp.ok && data.plano_semanal) { console.log("Resposta OK e plano_semanal encontrado. Chamando exibirPlanoSemanalFormatado."); setMsg(msg, data.message||`Plano gerado com sucesso!`, "success", 3000); planoAtualCache = data.plano_semanal; if(data.plano_semanal.id_treino_gerado) { planoAtualCache.id_treino_gerado = data.plano_semanal.id_treino_gerado; } exibirPlanoSemanalFormatado(planoAtualCache); const trigger = document.getElementById('plano-tab'); if(trigger) bootstrap.Tab.getOrCreateInstance(trigger).show(); } else { const errMsg = data.detail || "Erro desconhecido ao gerar o plano (resposta não OK ou dados inválidos)."; console.error("Falha ao gerar plano:", errMsg, "Dados recebidos:", data); setMsg(msg, errMsg, "error"); contTabela.innerHTML = `<div class="alert alert-danger">Falha ao gerar plano: ${errMsg}</div>`; titP.innerText = "Falha ao Gerar"; planoAtualCache = null; }
    } catch (e) { console.error("Erro durante fetch ou processamento em gerarPlanoSemanal:", e); if (e.message !== "Não autenticado" && e.message !== "Sessão expirada ou inválida") { setMsg(msg, "Erro de conexão ao gerar plano.", "error"); contTabela.innerHTML = `<div class="alert alert-danger">Erro de conexão. Verifique sua rede e tente novamente. Detalhe: ${e.message}</div>`; titP.innerText = "Erro de Conexão"; } planoAtualCache = null; }
}

// --- Regenerar Dia (Função existente, funcionalidade OK) ---
async function regenerarDia(buttonElement) {
    if (!alunoSelecionadoId) { alert("Erro: Aluno não selecionado."); return; }
    const diaKey = buttonElement.getAttribute('data-dia-key');
    const templateId = buttonElement.getAttribute('data-template-id');
    if (!diaKey || !templateId) { alert("Erro: Informações do dia ou template não encontradas no botão."); console.error("Missing data attributes on button:", buttonElement); return; }
    const tbodyParaAtualizar = document.getElementById(`tbody-dia-${diaKey}`);
    const msgContainer = document.getElementById("gerarTreinoMsg"); // Usar a msg da aba gerar, ou criar uma msg na aba plano?
    if (!tbodyParaAtualizar) { alert(`Erro: Não foi possível encontrar a área de exercícios para o Dia ${diaKey}.`); console.error(`Could not find tbody with id: tbody-dia-${diaKey}`); return; }
    const conteudoAntigoTbody = tbodyParaAtualizar.innerHTML;
    tbodyParaAtualizar.innerHTML = `<tr><td colspan="5" class="text-center p-4"><div class="loader"></div> Regenerando Dia ${diaKey}...</td></tr>`;
    buttonElement.disabled = true;
    if(msgContainer) setMsg(msgContainer, `Regenerando exercícios para o Dia ${diaKey}...`, "info");

    // Limpar o feedback específico deste dia ao regenerar
    if(feedbackDiaAtual[diaKey]) {
        delete feedbackDiaAtual[diaKey];
        const diaContainer = buttonElement.closest('.dia-treino-container'); // Encontra o container pai do dia
        if(diaContainer) {
             // Remove visualmente o 'active' dos botões de feedback deste dia
             diaContainer.querySelectorAll('.feedback-dia-btn.active').forEach(btn => btn.classList.remove('active'));
        }
    }

    try {
        const url = `${API_BASE_URL}/gerar_exercicios_dia/${alunoSelecionadoId}`;
        const payload = { dia_key: diaKey, template_id: templateId };
        console.log(`Chamando API para regenerar Dia ${diaKey}:`, url, payload);
        const resp = await fetchAutenticado(url, { method: "POST", headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        console.log(`API respondeu com status ${resp.status} para regeneração do Dia ${diaKey}.`);
        if (!resp.ok) {
            let errorData = { detail: `Erro HTTP ${resp.status}` };
            try { errorData = await resp.json(); } catch (e) { console.warn("Resposta de erro não era JSON");}
            throw new Error(errorData.detail || `Falha ao regenerar Dia ${diaKey}`);
        }
        const novosExercicios = await resp.json();

        // Atualiza o cache local do plano se ele existir
        if (planoAtualCache && planoAtualCache.dias_treino && planoAtualCache.dias_treino[diaKey]) {
            planoAtualCache.dias_treino[diaKey].exercicios = novosExercicios;
            console.log(`Cache do plano atualizado para o Dia ${diaKey}`);
            // Re-renderiza apenas o corpo da tabela do dia
            preencherTbodyDia(tbodyParaAtualizar, novosExercicios, diaKey);
        } else {
             console.warn("Cache do plano não encontrado ou inconsistente. Renderizando dia mas cache não atualizado.");
             preencherTbodyDia(tbodyParaAtualizar, novosExercicios, diaKey); // Tenta renderizar mesmo sem cache
        }

        if(msgContainer) setMsg(msgContainer, `Exercícios do Dia ${diaKey} atualizados!`, "success", 3000);

    } catch (e) {
        console.error(`Erro ao regenerar Dia ${diaKey}:`, e);
        if(msgContainer) setMsg(msgContainer, `Erro ao regenerar Dia ${diaKey}: ${e.message}`, "error");
        tbodyParaAtualizar.innerHTML = conteudoAntigoTbody; // Restaura conteúdo em caso de erro
    } finally {
        buttonElement.disabled = false; // Reabilita o botão
    }
}

// --- Função Exibir Plano (Modificada para adicionar botões de feedback por dia) ---
function exibirPlanoSemanalFormatado(planoData) {
    const tabelaContainer = document.getElementById("tabelaPlanoContainer");
    const nomeAlunoDiv = document.getElementById("nomeAlunoParaImpressao");
    const obsContainer = document.getElementById("observacoesGeraisContainer");
    const tit = document.getElementById("tituloPlanoGerado");
    const btnP = document.getElementById("botaoImprimir");
    const btnR = document.getElementById("botaoRegerar"); // Botão Gerar Outra Opção
    const feedbackSectionAntiga = document.getElementById('feedbackPlanoSection');
    const feedbackSectionNova = document.getElementById('feedbackGrupoSection');
    const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer');

    // Limpa estado anterior
    if (tabelaContainer) tabelaContainer.innerHTML = "";
    if (nomeAlunoDiv) nomeAlunoDiv.innerHTML = "";
    if (obsContainer) obsContainer.innerHTML = "";
    if (btnP) btnP.style.display = 'none';
    if (btnR) btnR.style.display = 'none';
    if (feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
    if(feedbackSectionNova) feedbackSectionNova.remove();
    if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

    // Limpa o estado do feedback por dia ao exibir um novo plano
    feedbackDiaAtual = {};

    if (!planoData?.plano_info || !planoData.dias_treino) {
        if(tabelaContainer) tabelaContainer.innerHTML = '<div class="alert alert-danger">Erro ao receber dados do plano ou plano vazio.</div>';
        if(tit) tit.innerText="Erro ao Carregar Plano"; planoAtualCache = null; return;
    }

    const idDoPlanoAtual = planoData.id_treino_gerado || planoData.plano_info?.id_treino_gerado || null;
    const templateIdAtual = planoData.plano_info?.template_id || null;

    if(tit) tit.innerText = `Plano de Treino - ${alunoSelecionadoNome || 'Aluno Atual'}`;
    if (nomeAlunoDiv && alunoSelecionadoNome) nomeAlunoDiv.innerHTML = `<h4>Aluno: ${alunoSelecionadoNome}</h4>`;

    try {
        const dias = Object.keys(planoData.dias_treino).sort();
        let temEx = false;

        dias.forEach(dia_key => {
            const dia_info = planoData.dias_treino[dia_key];
            if (!dia_info || !dia_info.exercicios || dia_info.exercicios.length === 0) return;
            temEx = true;

            const diaContainer = document.createElement('div');
            diaContainer.id = `dia-container-${dia_key}`;
            diaContainer.className = 'dia-treino-container mb-4'; // Classe para estilização

            const table = document.createElement('table');
            table.className = 'table table-bordered table-striped table-workout';

            const thead = table.createTHead();
            const headRow = thead.insertRow();
            const th = document.createElement('th');
            th.colSpan = 5; // Ajuste conforme o número de colunas
            th.className = 'table-primary text-center position-relative'; // Centralizado e com posição relativa

            // Conteúdo do cabeçalho: Título, Botões Feedback Dia, Botão Refazer
            th.innerHTML = `
                <span class="align-middle fw-bold me-3"><i class="bi bi-calendar-date me-2"></i> Dia ${dia_key}: ${dia_info.nome_dia || 'Treino'}</span>

                <div class="btn-group btn-group-sm feedback-dia-btn-group non-printable" role="group" aria-label="Feedback Dia ${dia_key}">
                    <button type="button" class="btn btn-outline-success feedback-dia-btn" data-dia-key="${dia_key}" data-feedback="Excelente" title="Excelente"><i class="bi bi-hand-thumbs-up"></i></button>
                    <button type="button" class="btn btn-outline-primary feedback-dia-btn" data-dia-key="${dia_key}" data-feedback="Bom" title="Bom"><i class="bi bi-emoji-smile"></i></button>
                    <button type="button" class="btn btn-outline-warning feedback-dia-btn" data-dia-key="${dia_key}" data-feedback="Médio" title="Médio"><i class="bi bi-emoji-neutral"></i></button>
                    <button type="button" class="btn btn-outline-danger feedback-dia-btn" data-dia-key="${dia_key}" data-feedback="Ruim" title="Ruim"><i class="bi bi-hand-thumbs-down"></i></button>
                </div>

                <button class="btn btn-sm btn-outline-secondary position-absolute top-50 end-0 translate-middle-y me-2 non-printable"
                        onclick="regenerarDia(this)"
                        data-dia-key="${dia_key}"
                        data-template-id="${templateIdAtual || ''}"
                        title="Regenerar exercícios para este dia">
                    <i class="bi bi-arrow-repeat"></i> Refazer Dia
                </button>`;

            headRow.appendChild(th);

            // Cabeçalho das colunas da tabela
            const colRow = thead.insertRow();
            colRow.innerHTML = `<th>Exercício</th><th>Séries</th><th>Reps</th><th>Descanso</th><th>Observação/Técnica</th>`;

            const tbody = table.createTBody();
            tbody.id = `tbody-dia-${dia_key}`; // ID para poder atualizar com 'regenerarDia'
            preencherTbodyDia(tbody, dia_info.exercicios, dia_key); // Função auxiliar para popular

            diaContainer.appendChild(table);
            if(tabelaContainer) tabelaContainer.appendChild(diaContainer);
        });

        if (obsContainer && Array.isArray(planoData.observacoes_gerais) && planoData.observacoes_gerais.length > 0) {
             obsContainer.innerHTML = `
                <div class="observacoes-gerais">
                    <h5><i class="bi bi-info-circle me-2"></i>Observações Gerais</h5>
                    <ul class="list-unstyled mb-0"></ul>
                </div>`;
            const obsUl = obsContainer.querySelector('ul');
            planoData.observacoes_gerais.forEach(obs => {
                const li = document.createElement('li'); li.textContent = obs; obsUl.appendChild(li);
            });
        } else if (obsContainer) {
            obsContainer.innerHTML = '';
        }

        // Adiciona botão de Salvar Feedback GERAL dos dias, se houver exercícios
        if (temEx && tabelaContainer) {
             const saveFeedbackDayContainer = document.createElement('div');
             saveFeedbackDayContainer.id = 'saveFeedbackDayBtnContainer'; // ID consistente
             saveFeedbackDayContainer.className = 'text-center mt-4 pt-3 border-top non-printable';
             saveFeedbackDayContainer.innerHTML = `
                 <button id="btnSalvarFeedbacksDia" type="button" class="btn btn-success">
                    <i class="bi bi-check-circle me-2"></i>Salvar Avaliações
                 </button>
                 <div class="msg mt-2 text-center" id="feedbackDiaMsg"></div>
             `;
             tabelaContainer.appendChild(saveFeedbackDayContainer);
        }

        // Adiciona listeners aos botões de feedback DEPOIS que eles foram criados
        adicionarListenersFeedbackDia();

        if (temEx) {
            if(btnP) btnP.style.display = 'inline-block';
             if(btnR) btnR.style.display = 'inline-block'; // Mostra botão Gerar Outra Opção
        }
        else {
            if(tabelaContainer) tabelaContainer.innerHTML += '<div class="alert alert-warning text-center">O plano gerado não contém exercícios.</div>';
            if (btnP) btnP.style.display = 'none';
             if(btnR) btnR.style.display = 'none';
        }

        planoAtualCache = planoData; // Armazena o plano no cache global

    } catch (e) {
        console.error("Erro ao formatar/exibir plano:", e);
        if(tabelaContainer) tabelaContainer.innerHTML = `<div class="alert alert-danger">Erro ao exibir o plano. Detalhes: ${e.message}.</div>`;
        if(tit) tit.innerText = "Erro ao Exibir Plano";
        if (nomeAlunoDiv) nomeAlunoDiv.innerHTML = "";
        if (obsContainer) obsContainer.innerHTML = ""; // Limpa obs
        planoAtualCache = null;
        const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer');
        if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();
    }
}

// --- Função Auxiliar para Preencher Tbody de um dia (sem alterações) ---
function preencherTbodyDia(targetTbody, exerciciosDoDia, dia_key) {
    targetTbody.innerHTML = ''; // Limpa antes de preencher
    if (!exerciciosDoDia || !Array.isArray(exerciciosDoDia) || exerciciosDoDia.length === 0) { targetTbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted p-3">Nenhum exercício para este dia.</td></tr>`; return; }
    exerciciosDoDia.forEach((item, index) => {
        const row = targetTbody.insertRow(); row.dataset.index = index; row.dataset.dia = dia_key;
        let nome = 'N/A', series = 'N/A', reps = 'N/A', desc = 'N/A', obs = ''; let chaveOriginal = null;
        if (item.tipo_item === 'exercicio_normal' && item.exercicio) { const ex = item.exercicio; chaveOriginal = ex.chave_original; nome = ex.nome || 'Nome Indefinido'; series = ex.series || '?'; reps = ex.repeticoes || '?'; desc = ex.descanso || '?'; obs = ex.observacao_tecnica || ''; if(chaveOriginal) row.dataset.chave = chaveOriginal; }
        else if (item.tipo_item === 'tecnica' && item.exercicio_1 && item.exercicio_2) { const ex1 = item.exercicio_1; const ex2 = item.exercicio_2; chaveOriginal = ex1.chave_original; nome = `<span class="tecnica-label">${(item.nome_tecnica || 'TÉCNICA').toUpperCase().replace(/_/g, ' ')}</span> ${ex1.nome || '?'} + ${ex2.nome || '?'}`; series = ex1.series || '?'; reps = `${ex1.repeticoes || '?'}/${ex2.repeticoes || '?'}`; desc = ex1.descanso || '?'; obs = item.instrucao || ''; if(ex1.chave_original) row.dataset.chave1 = ex1.chave_original; if(ex2.chave_original) row.dataset.chave2 = ex2.chave_original; if(chaveOriginal) row.dataset.chave = chaveOriginal; }
        else if (item.tipo_item === 'tecnica' && item.nome_tecnica === 'piramide' && item.exercicio) { const ex = item.exercicio; chaveOriginal = ex.chave_original; nome = `<span class="tecnica-label">PIRÂMIDE</span> ${ex.nome || 'Nome Indefinido'}`; series = ex.series || '?'; reps = ex.repeticoes || '?'; desc = ex.descanso || '?'; obs = ex.observacao_tecnica || item.instrucao || ''; if(chaveOriginal) row.dataset.chave = chaveOriginal; }
        else { nome = '<span class="text-danger">Item de treino inválido.</span>'; console.warn("Item de treino não reconhecido:", item); chaveOriginal = null; }
        row.innerHTML = `<td>${nome}</td><td class="text-center">${series}</td><td class="text-center">${reps}</td><td class="text-center">${desc}</td><td>${obs || ''}</td>`;
    });
}

// --- Imprimir ---
function imprimirPlano() { window.print(); }

// --- Histórico ---
async function carregarHistoricoAluno() {
     if (!alunoSelecionadoId) return; const msgH = document.getElementById('historicoMsg'); const pDiv = document.getElementById('historicoPlanos'); const mDiv = document.getElementById('historicoMedidas'); setMsg(msgH, "", null); if(pDiv) pDiv.innerHTML='<div class="text-center p-3"><div class="loader"></div> Carregando planos...</div>'; if(mDiv) mDiv.innerHTML='<div class="text-center p-3"><div class="loader"></div> Carregando avaliações...</div>'; try { const [pResp, mResp] = await Promise.all([ fetchAutenticado(`${API_BASE_URL}/alunos/${alunoSelecionadoId}/historico/planos`), fetchAutenticado(`${API_BASE_URL}/alunos/${alunoSelecionadoId}/historico/medidas`) ]); if (pResp.ok) { const pData = await pResp.json(); exibirHistoricoPlanos(pData); } else { if(pDiv) pDiv.innerHTML = '<div class="alert alert-warning">Falha ao carregar histórico de planos.</div>'; } if (mResp.ok) { const mData = await mResp.json(); exibirHistoricoMedidas(mData); } else { if(mDiv) mDiv.innerHTML = '<div class="alert alert-warning">Falha ao carregar histórico de avaliações.</div>'; historicoMedidasCompleto = []; } } catch (e) { if (e.message !== "Não autenticado" && e.message !== "Sessão expirada ou inválida") { setMsg(msgH, "Erro de conexão ao buscar histórico.", "error"); if(pDiv)pDiv.innerHTML='<div class="alert alert-danger">Erro de conexão.</div>'; if(mDiv) mDiv.innerHTML='<div class="alert alert-danger">Erro de conexão.</div>'; } historicoMedidasCompleto = []; }
}
function exibirHistoricoPlanos(planos) { const div = document.getElementById('historicoPlanos'); if (!div) return; div.innerHTML = ''; if (!planos?.length) { div.innerHTML += '<div class="historico-vazio">Nenhum plano anterior encontrado.</div>'; return; } const ul = document.createElement('ul'); ul.className='list-unstyled mb-0'; planos.slice(0, 15).forEach(p => { if (!p || typeof p.id_treino_gerado === 'undefined') return; ul.innerHTML += `<li class="historico-item"><span><strong>${formatDate(p.data_geracao)}</strong> <small class='text-muted'>- Template: ${p.nome_template||'?'}</small></span><button class="btn btn-sm btn-outline-primary py-0 px-1" onclick="visualizarPlanoHistorico(${p.id_treino_gerado})"><i class="bi bi-eye-fill me-1"></i> Ver</button></li>`; }); if (planos.length > 15) { ul.innerHTML += '<li class="text-muted small text-center mt-2">... (mostrando os 15 planos mais recentes)</li>'; } div.appendChild(ul); }
async function visualizarPlanoHistorico(treinoId) {
     if (!alunoSelecionadoId || !treinoId) { alert("Erro interno: dados inválidos para visualizar plano."); return; } const msgH = document.getElementById('historicoMsg'); const contTabela = document.getElementById("tabelaPlanoContainer"); const nomeAlunoDiv = document.getElementById("nomeAlunoParaImpressao"); const obsContainer = document.getElementById("observacoesGeraisContainer"); const titPlano = document.getElementById("tituloPlanoGerado"); if(msgH) setMsg(msgH, `Buscando plano ${treinoId}...`, "info"); if(contTabela) contTabela.innerHTML = '<div class="text-center p-5"><div class="loader"></div> Carregando plano do histórico...</div>'; if(nomeAlunoDiv) nomeAlunoDiv.innerHTML = ""; if(obsContainer) obsContainer.innerHTML = ""; if(titPlano) titPlano.innerText = "Carregando Plano...";
     feedbackDiaAtual = {}; // <<< Limpa estado do feedback por dia
     const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer'); if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove(); // Remove a seção de salvar
     const feedbackSectionNova = document.getElementById('feedbackGrupoSection'); if(feedbackSectionNova) feedbackSectionNova.remove(); // Remove seção antiga se existir

     try { const url = `${API_BASE_URL}/historico/planos/${treinoId}`; const resp = await fetchAutenticado(url); if (!resp.ok) { const errData = await resp.json().catch(() => ({ detail: `Erro ${resp.status}` })); throw new Error(errData.detail || `Erro ${resp.status} ao buscar plano.`); } const planoData = await resp.json(); if(planoData && !planoData.id_treino_gerado) { planoData.id_treino_gerado = treinoId; } if (planoData?.plano_info && planoData.dias_treino) { if(msgH) setMsg(msgH, ""); exibirPlanoSemanalFormatado(planoData); const trigger = document.getElementById('plano-tab'); if(trigger) bootstrap.Tab.getOrCreateInstance(trigger).show(); } else { throw new Error("Formato de plano recebido inválido."); }
     } catch (e) { if(msgH) setMsg(msgH, `Erro: ${e.message}`, "error"); if(contTabela) contTabela.innerHTML = `<div class="alert alert-danger">Falha ao carregar plano ${treinoId} do histórico.</div>`; if(titPlano) titPlano.innerText = "Erro ao Carregar"; if(nomeAlunoDiv) nomeAlunoDiv.innerHTML = ""; if(obsContainer) obsContainer.innerHTML = ""; planoAtualCache = null; }
}
function exibirHistoricoMedidas(medidas) {
    const div = document.getElementById('historicoMedidas'); if (!div) return; div.innerHTML = '';
    if (!medidas || !Array.isArray(medidas) || medidas.length === 0) { div.innerHTML = '<div class="historico-vazio">Nenhuma avaliação física anterior registrada.</div>'; historicoMedidasCompleto = []; return; }
    const medidasOrdenadas = [...medidas]; historicoMedidasCompleto = medidasOrdenadas;
    const ul = document.createElement('ul'); ul.className = 'list-unstyled mb-0';
    medidasOrdenadas.forEach((medidaAtual, index) => { if (!medidaAtual || (medidaAtual.id == null && medidaAtual.data_medicao == null)) return; const li = document.createElement('li'); li.className = 'historico-item'; const dataFormatada = formatDate(medidaAtual.data_medicao); const identificadorAvaliacao = medidaAtual.id != null ? medidaAtual.id : medidaAtual.data_medicao; if (identificadorAvaliacao == null) { li.innerHTML = `<span><strong>${dataFormatada || '?'}</strong> <span class="text-danger small">(Erro: ID inválido)</span></span>`; } else { li.innerHTML = `<span><strong>${dataFormatada || '?'}</strong></span><button class="btn btn-sm btn-outline-primary py-0 px-1" onclick="visualizarDetalhesAvaliacao('${identificadorAvaliacao}')"><i class="bi bi-eye-fill me-1"></i> Ver</button>`; } ul.appendChild(li); });
    if (ul.childElementCount === 0 && medidas.length > 0) { div.innerHTML = '<div class="historico-vazio">Erro ao processar avaliações.</div>'; } else if (ul.childElementCount === 0) { div.innerHTML = '<div class="historico-vazio">Nenhuma avaliação encontrada.</div>'; } else { div.appendChild(ul); } if (ul.childElementCount > 15) { const aviso = document.createElement('p'); aviso.className = 'text-muted small text-center mt-2 mb-0'; aviso.textContent = `... (mostrando as ${ul.childElementCount} avaliações mais recentes)`; div.appendChild(aviso); }
}
function visualizarDetalhesAvaliacao(identificadorAvaliacao) {
    const modalBody = document.getElementById('modalDetalhesAvaliacaoBody'); const modalTitle = document.getElementById('modalDetalhesAvaliacaoLabel'); const modal = document.getElementById('modalDetalhesAvaliacao');
    if (!modal || !modalBody || !modalTitle || !historicoMedidasCompleto) { console.error("Elementos do modal de detalhes ou cache de histórico não encontrados."); alert("Erro ao tentar mostrar detalhes da avaliação."); return; }
    let avaliacao = historicoMedidasCompleto.find(m => { if (m.id != null && String(m.id) === String(identificadorAvaliacao)) return true; if (m.id == null && m.data_medicao != null && m.data_medicao === identificadorAvaliacao) return true; return false; });
    if (!avaliacao) { console.error(`Avaliação com identificador '${identificadorAvaliacao}' não encontrada no cache.`); modalBody.innerHTML = '<div class="alert alert-warning">Detalhes não encontrados para esta avaliação.</div>'; modalTitle.innerText = 'Erro'; bootstrap.Modal.getOrCreateInstance(modal).show(); return; }
    modalTitle.innerText = `Avaliação de ${formatDate(avaliacao.data_medicao)}`;
    let detalhesHtml = '<dl class="row">';
    const camposParaExibir = [ { key: 'altura_cm', label: 'Altura', unit: 'cm' }, { key: 'peso_kg', label: 'Peso', unit: 'kg' }, { key: 'circ_ombros_cm', label: 'Ombros', unit: 'cm' }, { key: 'circ_peito_cm', label: 'Tórax', unit: 'cm' }, { key: 'circ_cintura_cm', label: 'Cintura', unit: 'cm' }, { key: 'circ_quadril_cm', label: 'Quadril', unit: 'cm' }, { key: 'circ_biceps_d_relaxado_cm', label: 'Bíc D. Rel', unit: 'cm' }, { key: 'circ_biceps_e_relaxado_cm', label: 'Bíc E. Rel', unit: 'cm' }, { key: 'circ_biceps_d_contraido_cm', label: 'Bíc D. Contr', unit: 'cm' }, { key: 'circ_biceps_e_contraido_cm', label: 'Bíc E. Contr', unit: 'cm' }, { key: 'circ_antebraco_d_cm', label: 'Anteb D.', unit: 'cm' }, { key: 'circ_antebraco_e_cm', label: 'Anteb E.', unit: 'cm' }, { key: 'circ_coxa_d_cm', label: 'Coxa D.', unit: 'cm' }, { key: 'circ_coxa_e_cm', label: 'Coxa E.', unit: 'cm' }, { key: 'circ_panturrilha_d_cm', label: 'Pant D.', unit: 'cm' }, { key: 'circ_panturrilha_e_cm', label: 'Pant E.', unit: 'cm' }, { key: 'dc_triceps_mm', label: 'DC Tríceps', unit: 'mm' }, { key: 'dc_subescapular_mm', label: 'DC Subescapular', unit: 'mm' }, { key: 'dc_peitoral_axilar_mm', label: 'DC Peit/Axilar', unit: 'mm' }, { key: 'dc_suprailiaca_mm', label: 'DC Supra-ilíaca', unit: 'mm' }, { key: 'dc_abdominal_mm', label: 'DC Abdominal', unit: 'mm' }, { key: 'dc_coxa_mm', label: 'DC Coxa', unit: 'mm' }, { key: 'dc_panturrilha_mm', label: 'DC Panturrilha', unit: 'mm' } ];
    let temAlgumDado = false;
    camposParaExibir.forEach(campo => { if (avaliacao[campo.key] != null && avaliacao[campo.key] !== '') { temAlgumDado = true; let valorFormatado = avaliacao[campo.key]; if (typeof valorFormatado === 'number') { valorFormatado = valorFormatado.toFixed(1); } detalhesHtml += `<dt class="col-sm-4">${campo.label}</dt><dd class="col-sm-8">${valorFormatado} ${campo.unit || ''}</dd>`; } });
    if (!temAlgumDado) { detalhesHtml += '<dd class="col-12"><p class="text-muted fst-italic mt-2">Nenhum dado específico registrado nesta avaliação.</p></dd>'; }
    detalhesHtml += '</dl>'; modalBody.innerHTML = detalhesHtml; bootstrap.Modal.getOrCreateInstance(modal).show();
}

// --- Atalhos para trocar de aba ---
function verHistoricoPlanosAluno() { if (!alunoSelecionadoId) { alert("Selecione um aluno primeiro."); return; } const trigger = document.getElementById('historico-tab'); if (trigger) { bootstrap.Tab.getOrCreateInstance(trigger).show(); } }
function verHistoricoMedidasAluno() { if (!alunoSelecionadoId) { alert("Selecione um aluno primeiro."); return; } const trigger = document.getElementById('historico-tab'); if (trigger) { bootstrap.Tab.getOrCreateInstance(trigger).show(); } }

// --- Modal Nova Avaliação ---
async function carregarUltimoPlanoAluno() {
    if (!alunoSelecionadoId) return; const contTabela = document.getElementById("tabelaPlanoContainer"); const nomeAlunoDiv = document.getElementById("nomeAlunoParaImpressao"); const obsContainer = document.getElementById("observacoesGeraisContainer"); const tit = document.getElementById("tituloPlanoGerado"); const msgH = document.getElementById('historicoMsg');
    feedbackDiaAtual = {}; // <<< Limpa estado do feedback por dia
    const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer'); if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

    if (contTabela) contTabela.innerHTML = '<div class="text-center p-5"><div class="loader"></div> Carregando último plano...</div>'; if (nomeAlunoDiv) nomeAlunoDiv.innerHTML = ""; if (obsContainer) obsContainer.innerHTML = ""; if (tit) tit.innerText = "Carregando..."; const feedbackSectionNova = document.getElementById('feedbackGrupoSection'); if(feedbackSectionNova) feedbackSectionNova.remove();
    try { const url = `${API_BASE_URL}/alunos/${alunoSelecionadoId}/plano/atual`; const resp = await fetchAutenticado(url); if (resp.status === 404) { if(contTabela) contTabela.innerHTML = '<div class="alert alert-secondary text-center">Nenhum plano recente encontrado para este aluno. Gere um novo.</div>'; if(tit) tit.innerText = "Plano Atual"; planoAtualCache = null; return; } if (!resp.ok) { const errData = await resp.json().catch(() => ({ detail: `Erro ${resp.status}` })); throw new Error(errData.detail || `Erro ${resp.status} ao buscar plano.`); } const planoData = await resp.json(); if(planoData && !planoData.id_treino_gerado && planoData.plano_info?.id_treino_gerado) { planoData.id_treino_gerado = planoData.plano_info.id_treino_gerado; } if (planoData?.plano_info && planoData.dias_treino) { exibirPlanoSemanalFormatado(planoData); if(msgH?.innerText.includes("Buscando")) setMsg(msgH, ""); } else { throw new Error("Formato de plano recebido inválido."); }
    } catch (e) { if (contTabela) contTabela.innerHTML = `<div class="alert alert-warning">Falha ao carregar último plano. (${e.message}) Tente gerar um novo.</div>`; if (tit) tit.innerText = "Plano Atual"; if (nomeAlunoDiv) nomeAlunoDiv.innerHTML = ""; if (obsContainer) obsContainer.innerHTML = ""; planoAtualCache = null; }
}

// --- Visualizar Dados Cadastrais ---
async function visualizarDadosCadastro() {
    if (!alunoSelecionadoId) { alert("Selecione um aluno para ver os dados."); return; } const modalBody = document.getElementById('modalDadosCadastroBody'); const modalTitle = document.getElementById('modalDadosCadastroLabel'); const modal = document.getElementById('modalDadosCadastro'); const historicoMsg = document.getElementById('historicoMsg'); if (!modalBody || !modal || !modalTitle || !historicoMsg) { console.error("Elementos do modal de dados cadastrais não encontrados."); return; } modalTitle.innerText = `Dados Cadastrais - ${alunoSelecionadoNome}`; modalBody.innerHTML = '<div class="text-center p-4"><div class="loader"></div> Carregando dados...</div>'; const modalInstance = bootstrap.Modal.getOrCreateInstance(modal); modalInstance.show(); setMsg(historicoMsg, "", null); try { const url = `${API_BASE_URL}/alunos/${alunoSelecionadoId}`; const response = await fetchAutenticado(url); if (!response.ok) { const errData = await response.json().catch(() => ({ detail: `Erro ${response.status}` })); throw new Error(errData.detail || `Falha ao buscar dados do aluno (${response.status})`); } const data = await response.json(); modalBody.innerHTML = ''; const dlBasicos = document.createElement('dl'); dlBasicos.classList.add('row'); dlBasicos.innerHTML = `<dt class="col-sm-4">Nome Completo</dt><dd class="col-sm-8">${data.nome || 'Não informado'}</dd><dt class="col-sm-4">Idade</dt><dd class="col-sm-8">${data.idade || 'Não informado'}</dd><dt class="col-sm-4">Sexo</dt><dd class="col-sm-8">${data.sexo || 'Não informado'}</dd><dt class="col-sm-4">Nível</dt><dd class="col-sm-8">${data.nivel || 'Não informado'}</dd>`; modalBody.appendChild(dlBasicos); const dlObjetivos = document.createElement('dl'); dlObjetivos.classList.add('row'); dlObjetivos.innerHTML = `<dt class="col-sm-4">Foco Principal</dt><dd class="col-sm-8">${data.foco_treino || 'Não informado'}</dd><dt class="col-sm-4">Lesão/Dor Ativa</dt><dd class="col-sm-8">${data.historico_lesoes || 'Nenhuma informada'}</dd><dt class="col-sm-4">Observações</dt><dd class="col-sm-8" style="white-space: pre-wrap;">${data.objetivos || 'Nenhuma observação'}</dd>`; modalBody.appendChild(dlObjetivos); const medidasData = data.medidas && typeof data.medidas === 'object' ? data.medidas : {}; const camposMedidasExibicao = [ { key: 'altura_cm', label: 'Altura (cm)' }, { key: 'peso_kg', label: 'Peso (kg)' }, { key: 'circ_ombros_cm', label: 'Ombros (cm)' }, { key: 'circ_peito_cm', label: 'Tórax (cm)' }, { key: 'circ_cintura_cm', label: 'Cintura (cm)' }, { key: 'circ_quadril_cm', label: 'Quadril (cm)' }, { key: 'circ_biceps_d_relaxado_cm', label: 'Bíc D. Rel (cm)' }, { key: 'circ_biceps_e_relaxado_cm', label: 'Bíc E. Rel (cm)' }, { key: 'circ_biceps_d_contraido_cm', label: 'Bíc D. Contr (cm)' }, { key: 'circ_biceps_e_contraido_cm', label: 'Bíc E. Contr (cm)' }, { key: 'circ_antebraco_d_cm', label: 'Anteb D. (cm)' }, { key: 'circ_antebraco_e_cm', label: 'Anteb E. (cm)' }, { key: 'circ_coxa_d_cm', label: 'Coxa D. (cm)' }, { key: 'circ_coxa_e_cm', label: 'Coxa E. (cm)' }, { key: 'circ_panturrilha_d_cm', label: 'Pant D. (cm)' }, { key: 'circ_panturrilha_e_cm', label: 'Pant E. (cm)' }, { key: 'dc_triceps_mm', label: 'DC Tríceps (mm)' }, { key: 'dc_subescapular_mm', label: 'DC Subescapular (mm)' }, { key: 'dc_peitoral_axilar_mm', label: 'DC Peit/Axilar (mm)' }, { key: 'dc_suprailiaca_mm', label: 'DC Supra-ilíaca (mm)' }, { key: 'dc_abdominal_mm', label: 'DC Abdominal (mm)' }, { key: 'dc_coxa_mm', label: 'DC Coxa (mm)' }, { key: 'dc_panturrilha_mm', label: 'DC Panturrilha (mm)' } ]; const medidasPreenchidas = camposMedidasExibicao.filter(item => medidasData[item.key] != null && medidasData[item.key] !== ''); if (medidasPreenchidas.length > 0) { const h5Medidas = document.createElement('h5'); h5Medidas.innerHTML = '<i class="bi bi-rulers me-2"></i>Medidas (Última Avaliação)'; modalBody.appendChild(h5Medidas); const gridMedidas = document.createElement('div'); gridMedidas.className = 'medidas-grid'; medidasPreenchidas.forEach(item => { const medidaDiv = document.createElement('div'); medidaDiv.className = 'medida-item'; medidaDiv.innerHTML = `<strong>${item.label}:</strong> ${medidasData[item.key]}`; gridMedidas.appendChild(medidaDiv); }); modalBody.appendChild(gridMedidas); } else { const pSemMedidas = document.createElement('p'); pSemMedidas.className = 'text-muted fst-italic mt-3'; pSemMedidas.textContent = 'Nenhuma medida específica foi registrada na última avaliação.'; modalBody.appendChild(pSemMedidas); } } catch (error) { console.error("Erro ao buscar dados cadastrais:", error); modalBody.innerHTML = `<div class="alert alert-danger">Erro ao carregar dados: ${error.message}</div>`; setMsg(historicoMsg, `Erro ao carregar dados cadastrais: ${error.message}`, "error", 5000); }
}
function abrirModalNovaAvaliacao() {
     if (!alunoSelecionadoId) { alert("Selecione um aluno primeiro!"); return; }
     // Busca dados atuais do aluno para pré-preencher o nível no modal
     visualizarDadosCadastro().then(() => { // Chama a função que busca e (indiretamente) preenche o modal
         const modal = document.getElementById('modalNovaAvaliacao');
         const modalTitle = document.getElementById('modalNovaAvaliacaoLabel');
         const nivelSelect = document.getElementById('m_nivel_aluno');
         const nivelOriginalInput = document.getElementById('m_nivel_original_aluno');
         const modalMsg = document.getElementById('modalMsg');
         // A busca já foi feita, agora só pegamos os dados do aluno para o nível
         const alunoAtualCompleto = historicoMedidasCompleto && historicoMedidasCompleto.length > 0 ? historicoMedidasCompleto[0] : null; // Pega a ultima medida para ter o aluno? Não, precisa buscar o aluno mesmo.
          // *** MELHORIA: Buscar dados do aluno aqui se não tiver no cache ***
          // Como visualizarDadosCadastro já foi chamado, vamos assumir que os dados estão no modal ou acessíveis
          // Esta parte é frágil, idealmente buscaria os dados do aluno aqui novamente se necessário.
          // Vamos usar os dados do `alunoSelecionadoNome` como fallback
          if (modalTitle) modalTitle.innerText = `Nova Avaliação - ${alunoSelecionadoNome}`;
          // Tenta pegar o nível atual do plano cacheado ou do modal
          const nivelAtual = planoAtualCache?.plano_info?.nivel || document.querySelector('#modalDadosCadastro dd:nth-of-type(4)')?.textContent || 'Iniciante'; // Fallback
          if (nivelSelect) nivelSelect.value = nivelAtual;
          if (nivelOriginalInput) nivelOriginalInput.value = nivelAtual;
          if (modalMsg) setMsg(modalMsg, '', null); // Limpa msg
          if (modal) bootstrap.Modal.getOrCreateInstance(modal).show();
     }).catch(err => {
          alert("Erro ao buscar dados do aluno para preencher o modal.");
          console.error("Erro em visualizarDadosCadastro antes de abrir modal:", err);
     });
}
async function salvarNovaMedicao() {
    if (!alunoSelecionadoId) { alert("Erro: Aluno não selecionado."); return; }
    const modalMsg = document.getElementById('modalMsg');
    const btnSalvar = document.querySelector('#modalNovaAvaliacao .modal-footer button.btn-primary');
    if(!modalMsg || !btnSalvar) return;

    setMsg(modalMsg, "Salvando avaliação...", "info");
    btnSalvar.disabled = true;

    const medidas = {};
    const camposMedidasModal = ['m_altura_cm','m_peso_kg','m_circ_ombros_cm','m_circ_peito_cm','m_circ_cintura_cm','m_circ_quadril_cm','m_circ_biceps_d_relaxado_cm','m_circ_biceps_e_relaxado_cm','m_circ_biceps_d_contraido_cm','m_circ_biceps_e_contraido_cm','m_circ_antebraco_d_cm','m_circ_antebraco_e_cm','m_circ_coxa_d_cm','m_circ_coxa_e_cm','m_circ_panturrilha_d_cm','m_circ_panturrilha_e_cm','m_dc_triceps_mm','m_dc_subescapular_mm','m_dc_peitoral_axilar_mm','m_dc_suprailiaca_mm','m_dc_abdominal_mm','m_dc_coxa_mm','m_dc_panturrilha_mm'];
    let algumaMedidaPreenchida = false;
    camposMedidasModal.forEach(id => {
        const el = document.getElementById(id);
        const v = el ? el.value.trim() : null;
        if(v) {
            const n = parseFloat(v);
            if(!isNaN(n) && n >= 0) {
                const backendKey = el.name; // Pega o nome do input que deve corresponder à chave no Pydantic
                if(backendKey) {
                    medidas[backendKey] = n;
                    algumaMedidaPreenchida = true;
                }
            }
        }
    });

    // Verifica se o nível do aluno foi alterado
    const nivelSelect = document.getElementById('m_nivel_aluno');
    const nivelOriginalInput = document.getElementById('m_nivel_original_aluno');
    const nivelNovo = nivelSelect ? nivelSelect.value : null;
    const nivelOriginal = nivelOriginalInput ? nivelOriginalInput.value : null;
    const nivelFoiAlterado = nivelNovo && nivelOriginal && nivelNovo !== nivelOriginal;

    if (!algumaMedidaPreenchida && !nivelFoiAlterado) {
         setMsg(modalMsg, "Nenhuma medida foi preenchida e o nível não foi alterado.", "warning", 4000);
         btnSalvar.disabled = false;
         return;
    }

    let promessas = [];

    // 1. Salva as medidas se houver alguma
    if (algumaMedidaPreenchida) {
         const urlMedidas = `${API_BASE_URL}/alunos/${alunoSelecionadoId}/medidas`;
         promessas.push(
             fetchAutenticado(urlMedidas, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(medidas) })
                 .then(async response => {
                      if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || `Erro ${response.status} ao salvar medidas.`); }
                      return response.json();
                 })
         );
    }

    // 2. Atualiza o nível do aluno se foi alterado
    if (nivelFoiAlterado) {
        const urlNivel = `${API_BASE_URL}/alunos/${alunoSelecionadoId}`;
        const payloadNivel = { nivel: nivelNovo }; // Usa o modelo AlunoUpdate
        promessas.push(
            fetchAutenticado(urlNivel, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payloadNivel) })
                .then(async response => {
                    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || `Erro ${response.status} ao atualizar nível.`); }
                    return response.json();
                })
        );
    }

    // Executa todas as operações necessárias
    try {
        const resultados = await Promise.all(promessas);
        let msgSucesso = [];
        resultados.forEach(res => { if(res?.message) msgSucesso.push(res.message); });

        setMsg(modalMsg, msgSucesso.join(' ') || "Operação concluída.", "success", 3000);
        // Fecha modal após um tempo
        setTimeout(() => {
             const modalEl = document.getElementById('modalNovaAvaliacao');
             const modalInstance = bootstrap.Modal.getInstance(modalEl);
             modalInstance?.hide();
             // Recarrega o histórico na aba correta
             const activeTab = document.querySelector('#mainTabs .nav-link.active');
             if (activeTab && activeTab.getAttribute('data-bs-target') === '#historico') {
                 carregarHistoricoAluno();
             }
        }, 1500);
    } catch (error) {
         console.error("Erro ao salvar nova avaliação/nível:", error);
         setMsg(modalMsg, `Erro: ${error.message}`, "error");
    } finally {
         btnSalvar.disabled = false;
    }
}

// === NOVO: Funções para Feedback por Dia ===
function adicionarListenersFeedbackDia() {
    document.querySelectorAll('.feedback-dia-btn-group .feedback-dia-btn').forEach(button => {
          const newButton = button.cloneNode(true); button.parentNode.replaceChild(newButton, button);
    });
    document.querySelectorAll('.feedback-dia-comment-btn').forEach(button => {
          const newButton = button.cloneNode(true); button.parentNode.replaceChild(newButton, button);
    });
    document.querySelectorAll('.feedback-dia-btn-group .feedback-dia-btn').forEach(button => {
        button.addEventListener('click', function() {
            const diaKey = this.dataset.diaKey; const feedback = this.dataset.feedback;
            this.closest('.feedback-dia-btn-group').querySelectorAll('.feedback-dia-btn').forEach(btn => btn.classList.remove('active'));
            this.classList.add('active'); feedbackDiaAtual[diaKey] = feedback;
            console.log(`Feedback para Dia ${diaKey}: ${feedback}`); console.log("Estado atual:", feedbackDiaAtual);
        });
    });
    const btnSalvar = document.getElementById('btnSalvarFeedbacksDia');
    if (btnSalvar) {
          btnSalvar.replaceWith(btnSalvar.cloneNode(true));
          const newBtnSalvar = document.getElementById('btnSalvarFeedbacksDia');
          if(newBtnSalvar) newBtnSalvar.addEventListener('click', enviarFeedbackPorDia);
    } else { console.warn("Botão 'Salvar Avaliações' não encontrado para adicionar listener."); }
}
// --- FUNÇÃO ATUALIZADA PARA CHAMAR API ---
async function enviarFeedbackPorDia() {
    const feedbackMsgEl = document.getElementById('feedbackDiaMsg');
    const btnSalvar = document.getElementById('btnSalvarFeedbacksDia');
    if (!feedbackMsgEl || !btnSalvar) { console.error("Elementos necessários para feedback por dia (Msg, Botão) não encontrados."); return; }

    const feedbacksParaEnviar = {}; let algumFeedbackSelecionado = false;
    for (const diaKey in feedbackDiaAtual) {
        if (feedbackDiaAtual[diaKey]) {
            feedbacksParaEnviar[diaKey.toUpperCase()] = { feedback: feedbackDiaAtual[diaKey] }; // Formato { feedbacks: { DIA: { feedback: "Valor" } } }
            algumFeedbackSelecionado = true;
        }
    }
    if (!algumFeedbackSelecionado) { setMsg(feedbackMsgEl, "Selecione uma avaliação (Excelente, Bom...) para pelo menos um dia.", "warning", 4000); return; }

    const planoId = planoAtualCache?.id_treino_gerado;
    if (!planoId) { setMsg(feedbackMsgEl, "Erro: ID do plano atual não encontrado para salvar feedback.", "error", 5000); return; }

    const payload = { feedbacks: feedbacksParaEnviar }; // Payload correto para o Pydantic model
    console.log(`Enviando feedback para Plano ID ${planoId}:`, payload);

    setMsg(feedbackMsgEl, "Salvando avaliações...", "info");
    btnSalvar.disabled = true;
    const loader = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ';
    btnSalvar.innerHTML = loader + "Salvando...";

    // *** CHAMADA REAL À API ***
    try {
        const url = `${API_BASE_URL}/feedback/plano/${planoId}/dias`; // O NOVO ENDPOINT
        const response = await fetchAutenticado(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload) // Envia o payload formatado
        });
        const data = await response.json(); // Tenta ler o JSON da resposta

        if (response.ok) {
            setMsg(feedbackMsgEl, data.message || "Avaliações salvas com sucesso!", "success", 4000);
            // Limpa estado visual dos botões após sucesso
            document.querySelectorAll('.feedback-dia-btn.active').forEach(b => b.classList.remove('active'));
            feedbackDiaAtual = {}; // Limpa o estado interno também
        } else {
            setMsg(feedbackMsgEl, data.detail || `Erro ${response.status} ao salvar avaliações.`, "error", 5000);
        }
    } catch (e) {
        if (e.message !== "Não autenticado" && e.message !== "Sessão expirada ou inválida") {
            setMsg(feedbackMsgEl, "Erro de comunicação ao salvar avaliações.", "error", 5000);
            console.error("Erro fetch feedback dia:", e);
        }
         // Se der erro de autenticação, o fetchAutenticado já deve ter tratado/redirecionado.
    } finally {
        btnSalvar.disabled = false;
        btnSalvar.innerHTML = '<i class="bi bi-check-circle me-2"></i>Salvar Avaliações';
    }
}
// === Fim Funções para Feedback por Dia ===


// --- Funções de Substituição de Exercício (Mantidas como no original) ---
let exercicioParaSubstituir = null; // { diaKey: 'A', index: 0, chaveOriginal: 'remada_curvada_barra' }

function abrirModalSubstituirExercicio(buttonElement) {
    const row = buttonElement.closest('tr');
    if (!row) { console.error("Não foi possível encontrar a linha do exercício."); return; }

    const diaKey = row.dataset.dia;
    const index = parseInt(row.dataset.index);
    const chaveOriginal = row.dataset.chave || row.dataset.chave1;

    if (diaKey === undefined || index === undefined || !planoAtualCache || !planoAtualCache.dias_treino[diaKey] || !planoAtualCache.dias_treino[diaKey].exercicios[index]) {
          console.error("Dados do plano ou exercício para substituição inconsistentes.", { diaKey, index, planoAtualCache });
          alert("Erro ao preparar substituição. Dados do plano inconsistentes."); return;
    }
    if (!chaveOriginal) { console.warn("Chave original do exercício não encontrada para buscar alternativas."); }

    exercicioParaSubstituir = { diaKey, index, chaveOriginal };
    console.log("Preparando substituição para:", exercicioParaSubstituir);

    const modalEl = document.getElementById('modalSubstituirExercicio');
    const modalTitle = document.getElementById('modalSubstituirExercicioLabel');
    const exercicioAtualInfoDiv = document.getElementById('substituirExercicioAtualInfo');
    const alternativasContainer = document.getElementById('substituirAlternativasContainer');
    const btnConfirmar = document.getElementById('btnConfirmarSubstituicao');
    const msgSubstituir = document.getElementById('substituirMsg');

    if (!modalEl || !modalTitle || !exercicioAtualInfoDiv || !alternativasContainer || !btnConfirmar || !msgSubstituir) { console.error("Elementos do modal de substituição não encontrados!"); return; }

    const itemOriginal = planoAtualCache.dias_treino[diaKey].exercicios[index]; let nomeExAtual = 'Nome Indefinido';
    if (itemOriginal.tipo_item === 'exercicio_normal' && itemOriginal.exercicio) { nomeExAtual = itemOriginal.exercicio.nome || nomeExAtual; }
    else if (itemOriginal.tipo_item === 'tecnica' && itemOriginal.exercicio_1) { let nomeTec = (itemOriginal.nome_tecnica || 'TÉCNICA').toUpperCase().replace(/_/g, ' '); if (itemOriginal.exercicio_2) { nomeExAtual = `${nomeTec}: ${itemOriginal.exercicio_1.nome || '?'} + ${itemOriginal.exercicio_2.nome || '?'}`; } else if (itemOriginal.exercicio) { nomeExAtual = `${nomeTec}: ${itemOriginal.exercicio.nome || '?'}`; } else { nomeExAtual = `${nomeTec}: Exercício(s) Indefinidos`; } }
    exercicioAtualInfoDiv.innerHTML = `<p><strong>Nome:</strong> ${nomeExAtual}</p><p><strong>Grupo:</strong> ${itemOriginal.exercicio?.grupo || itemOriginal.exercicio_1?.grupo || 'Não informado'}</p>`;
    alternativasContainer.innerHTML = '<div class="text-center p-3"><div class="loader"></div> Buscando alternativas...</div>'; btnConfirmar.disabled = true; setMsg(msgSubstituir, '', null);

    if (chaveOriginal) { buscarAlternativasExercicio(chaveOriginal, alternativasContainer, btnConfirmar, msgSubstituir); }
    else { alternativasContainer.innerHTML = '<div class="alert alert-warning">Não foi possível buscar alternativas: Chave do exercício não encontrada.</div>'; btnConfirmar.disabled = true; }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}
async function buscarAlternativasExercicio(chaveOriginal, containerElement, btnConfirmar, msgElement) {
     try {
        const url = `${API_BASE_URL}/exercicios/alternativas/${chaveOriginal}`; console.log("Buscando alternativas:", url); const response = await fetchAutenticado(url);
        if (!response.ok) { const errData = await response.json().catch(() => ({ detail: `Erro HTTP ${response.status}` })); throw new Error(errData.detail || `Falha ao buscar alternativas (${response.status}).`); }
        const alternativas = await response.json(); console.log("Alternativas recebidas:", alternativas);
        containerElement.innerHTML = '';
        if (!alternativas || alternativas.length === 0) { containerElement.innerHTML = '<div class="alert alert-secondary">Nenhuma alternativa sugerida encontrada.</div>'; btnConfirmar.disabled = true; return; }
        const ul = document.createElement('ul'); ul.className = 'list-group';
        alternativas.forEach(alt => { if (!alt || !alt.chave || !alt.nome) return; const li = document.createElement('li'); li.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center'; li.innerHTML = `${alt.nome} <button type="button" class="btn btn-outline-primary btn-sm" data-alt-chave="${alt.chave}">Selecionar</button>`; li.dataset.chave = alt.chave; li.querySelector('button').addEventListener('click', function() { containerElement.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active')); li.classList.add('active'); btnConfirmar.disabled = false; }); ul.appendChild(li); }); containerElement.appendChild(ul);
     } catch (error) { console.error("Erro ao buscar alternativas:", error); containerElement.innerHTML = `<div class="alert alert-danger">Erro ao buscar alternativas: ${error.message}</div>`; btnConfirmar.disabled = true; setMsg(msgElement, `Erro ao carregar alternativas: ${error.message}`, 'error'); }
}


// --- Inicialização e Listeners ---
document.addEventListener('DOMContentLoaded', () => {
    const existingToken = getToken(); const existingUsername = getUsername();
    if (existingToken && existingUsername) { storeUsername(existingUsername); showMainApp(); }
    else { document.getElementById('authDiv').style.display = 'block'; document.getElementById('mainAppDiv').style.display = 'none'; }

    document.querySelectorAll('#mainTabs button[data-bs-toggle="tab"]').forEach(tabEl => {
        tabEl.addEventListener('shown.bs.tab', event => {
            const targetPaneId = event.target.getAttribute('data-bs-target');
            const btnVerDadosContainer = document.getElementById("historicoHeaderActions");
            const feedbackSectionAntiga = document.getElementById('feedbackPlanoSection');
            const feedbackSectionNova = document.getElementById('feedbackGrupoSection');
            const saveFeedbackDayBtnContainer = document.getElementById('saveFeedbackDayBtnContainer');

            if (targetPaneId === '#historico') {
                const histInfo = document.getElementById("historicoAlunoInfo");
                if (alunoSelecionadoId) { if(histInfo) histInfo.innerHTML = `Histórico: <strong>${alunoSelecionadoNome}</strong>`; if(btnVerDadosContainer) btnVerDadosContainer.style.display = 'block'; carregarHistoricoAluno(); }
                else { if(histInfo) histInfo.innerHTML = `Selecione um aluno`; if(btnVerDadosContainer) btnVerDadosContainer.style.display = 'none'; const histP = document.getElementById('historicoPlanos'); const histM = document.getElementById('historicoMedidas'); if(histP) histP.innerHTML='<div class="historico-vazio">Selecione aluno na aba "Alunos/Gerar" para ver o histórico.</div>'; if(histM) histM.innerHTML='<div class="historico-vazio">Selecione aluno na aba "Alunos/Gerar" para ver o histórico.</div>'; }
                 if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
                 if(feedbackSectionNova) feedbackSectionNova.remove();
                 if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();

            } else if (targetPaneId === '#plano') {
                const contTabela = document.getElementById("tabelaPlanoContainer"); const nomeAlunoDiv = document.getElementById("nomeAlunoParaImpressao"); const obsContainer = document.getElementById("observacoesGeraisContainer"); const tit = document.getElementById("tituloPlanoGerado"); const btnP = document.getElementById("botaoImprimir"); const btnR = document.getElementById("botaoRegerar");
                 if(btnVerDadosContainer) btnVerDadosContainer.style.display = 'none';
                if (alunoSelecionadoId && !planoAtualCache) { carregarUltimoPlanoAluno(); }
                else if (planoAtualCache) { exibirPlanoSemanalFormatado(planoAtualCache); }
                else {
                     if(contTabela) contTabela.innerHTML='<div class="alert alert-info text-center">Selecione um aluno e gere um plano ou veja o histórico para exibir aqui.</div>';
                     if(tit) tit.innerText = "Plano Atual"; if(nomeAlunoDiv) nomeAlunoDiv.innerHTML = ""; if(obsContainer) obsContainer.innerHTML = ""; if(btnP) btnP.style.display='none'; if(btnR) btnR.style.display='none';
                     if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
                     if(feedbackSectionNova) feedbackSectionNova.remove();
                     if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();
                 }
            }
             else { // Outras abas como #gerarTreino ou #cadastro
                 if(btnVerDadosContainer) btnVerDadosContainer.style.display = 'none';
                 if(feedbackSectionAntiga) feedbackSectionAntiga.style.display = 'none';
                 if(feedbackSectionNova) feedbackSectionNova.remove();
                 if(saveFeedbackDayBtnContainer) saveFeedbackDayBtnContainer.remove();
             }
        });
    });

    // Listeners para limpar Modais ao fechar
    document.querySelectorAll('.modal').forEach(modalEl => {
      if(modalEl.id === 'modalNovaAvaliacao'){ modalEl.addEventListener('hidden.bs.modal', event => { modalEl.querySelectorAll('input[type="number"]').forEach(input => input.value = ''); const selectNivelEl = document.getElementById('m_nivel_aluno'); const nivelOriginalEl = document.getElementById('m_nivel_original_aluno'); if(selectNivelEl) selectNivelEl.value = 'Iniciante'; if(nivelOriginalEl) nivelOriginalEl.value = ''; const modalMsg = document.getElementById('modalMsg'); if(modalMsg) setMsg(modalMsg, '', null); }); }
       else if(modalEl.id === 'modalDadosCadastro') { modalEl.addEventListener('hidden.bs.modal', event => { const modalBody = document.getElementById('modalDadosCadastroBody'); if(modalBody) modalBody.innerHTML = '<p class="text-center text-muted">Carregando dados do aluno...</p>'; }); }
        else if(modalEl.id === 'modalDetalhesAvaliacao') { modalEl.addEventListener('hidden.bs.modal', event => { const modalBody = document.getElementById('modalDetalhesAvaliacaoBody'); if(modalBody) modalBody.innerHTML = '<p class="text-center text-muted">Carregando detalhes...</p>'; const modalTitle = document.getElementById('modalDetalhesAvaliacaoLabel'); if(modalTitle) modalTitle.innerText = 'Detalhes da Avaliação'; }); }
       else if(modalEl.id === 'modalSubstituirExercicio') { modalEl.addEventListener('hidden.bs.modal', event => { document.getElementById('substituirExercicioAtualInfo').innerHTML = '<p class="placeholder-glow"><span class="placeholder col-8"></span></p>'; document.getElementById('substituirAlternativasContainer').innerHTML = '<p class="text-muted">Carregando sugestões...</p>'; document.getElementById('btnConfirmarSubstituicao').disabled = true; const msgSubstituir = document.getElementById('substituirMsg'); if(msgSubstituir) setMsg(msgSubstituir, '', null);
            exercicioParaSubstituir = null; // Limpa o objeto de controle
        });
       }
    });

    // Listener para o botão "Confirmar Substituição" (Lógica de simulação mantida)
    const btnConfirmarSubstituicao = document.getElementById('btnConfirmarSubstituicao');
    if (btnConfirmarSubstituicao) {
         btnConfirmarSubstituicao.addEventListener('click', function() {
             if (!exercicioParaSubstituir || !planoAtualCache) { console.error("Dados para substituição ausentes."); setMsg(document.getElementById('substituirMsg'), "Erro: Dados do exercício a substituir não encontrados.", 'error'); return; }
             const alternativasContainer = document.getElementById('substituirAlternativasContainer'); const alternativaSelecionadaLi = alternativasContainer.querySelector('.list-group-item.active');
             if (!alternativaSelecionadaLi) { setMsg(document.getElementById('substituirMsg'), "Selecione uma alternativa antes de confirmar.", 'warning'); return; }
             const novaChaveExercicio = alternativaSelecionadaLi.dataset.chave;
             if (!novaChaveExercicio) { console.error("Chave da alternativa selecionada não encontrada."); setMsg(document.getElementById('substituirMsg'), "Erro: Chave da alternativa selecionada inválida.", 'error'); return; }
             console.log(`Confirmando substituição: Dia ${exercicioParaSubstituir.diaKey}, Índice ${exercicioParaSubstituir.index} por ${novaChaveExercicio}`);
             setMsg(document.getElementById('substituirMsg'), "Simulando substituição...", 'info'); this.disabled = true;
             const modalEl = document.getElementById('modalSubstituirExercicio'); const modalInstance = bootstrap.Modal.getInstance(modalEl);
             // *** SIMULAÇÃO DE SUBSTITUIÇÃO NO CACHE E RE-RENDER ***
             if (planoAtualCache && planoAtualCache.dias_treino && planoAtualCache.dias_treino[exercicioParaSubstituir.diaKey] && planoAtualCache.dias_treino[exercicioParaSubstituir.diaKey].exercicios[exercicioParaSubstituir.index]) {
                 const itemOriginal = planoAtualCache.dias_treino[exercicioParaSubstituir.diaKey].exercicios[exercicioParaSubstituir.index]; const novaAlternativaNome = alternativaSelecionadaLi.innerText.replace(' Selecionar', '').trim();
                 if (itemOriginal.tipo_item === 'exercicio_normal') { itemOriginal.exercicio.chave_original = novaChaveExercicio; itemOriginal.exercicio.nome = novaAlternativaNome; }
                 else if (itemOriginal.tipo_item === 'tecnica') { if (itemOriginal.exercicio) { itemOriginal.exercicio.chave_original = novaChaveExercicio; itemOriginal.exercicio.nome = novaAlternativaNome; } else if (itemOriginal.exercicio_1) { itemOriginal.exercicio_1.chave_original = novaChaveExercicio; itemOriginal.exercicio_1.nome = novaAlternativaNome; } }
                 const tbodyParaAtualizar = document.getElementById(`tbody-dia-${exercicioParaSubstituir.diaKey}`); if(tbodyParaAtualizar) { preencherTbodyDia(tbodyParaAtualizar, planoAtualCache.dias_treino[exercicioParaSubstituir.diaKey].exercicios, exercicioParaSubstituir.diaKey); }
                 console.log("Simulação: Exercício substituído no cache frontend."); setMsg(document.getElementById('substituirMsg'), `Simulação: Exercício substituído por "${novaAlternativaNome}"! (Necessita de backend para salvar)`, 'info', 6000);
                  setTimeout(() => { modalInstance?.hide(); this.disabled = false; }, 2000);
              } else { console.error("Erro interno: Plano atual ou exercício não encontrado no cache."); setMsg(document.getElementById('substituirMsg'), "Erro interno ao simular.", 'error'); this.disabled = false; }
             // *** FIM SIMULAÇÃO ***
         });
    }

    // Listener para o botão "Gerar Outra Opção" (regera o plano completo)
    const btnRegenerarPlanoCompleto = document.getElementById('botaoRegerar');
    if(btnRegenerarPlanoCompleto) {
        btnRegenerarPlanoCompleto.addEventListener('click', function() { gerarPlanoSemanal(); });
    }

}); // Fim DOMContentLoaded
