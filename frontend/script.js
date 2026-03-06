const API_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1') 
    ? 'http://127.0.0.1:8000' 
    : window.location.origin;
const Toast = Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 3000 });
const diasNome = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

let dataAtualCalendario = new Date();
let listaGlobalAlunos = [];

// --- NAVEGAÇÃO ENTRE ABAS ---
function trocarAba(aba) {
    document.querySelectorAll('.aba-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

    const idAba = 'aba' + aba.charAt(0).toUpperCase() + aba.slice(1);
    const idBtn = 'btnTab' + aba.charAt(0).toUpperCase() + aba.slice(1);
    
    document.getElementById(idAba).classList.remove('hidden');
    document.getElementById(idBtn).classList.add('active');

    if(aba === 'agenda') carregarAgenda();
    if(aba === 'alunos') carregarAlunos();
    if(aba === 'turmas') carregarTurmas();
    if(aba === 'grade') carregarTudoGrade();
    if(aba === 'historico') carregarHistoricoGeral();
}

async function fetchProtegido(url, opcoes = {}) {
    const token = localStorage.getItem('token_professor');
    
    const cabecalhos = {
        ...opcoes.headers,
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };

    try {
        const resposta = await fetch(url, { ...opcoes, headers: cabecalhos });

        if (resposta.status === 401) {
            localStorage.removeItem('token_professor');
            // Se estiver no painel e der 401, manda pro login
            if (document.getElementById('listaAgenda')) {
                window.location.href = "/frontend/login.html";
            }
            return { ok: false, json: async () => [] }; 
        }

        if (!resposta.ok) return { ok: false, json: async () => [] };

        return resposta;
    } catch (error) {
        console.error("Erro na requisição:", error);
        return { ok: false, json: async () => [] };
    }
}

// --- GESTÃO DE ALUNOS (COM NOVOS CAMPOS E CORREÇÃO 422) ---
async function carregarAlunos() {
    const container = document.getElementById('listaAlunos');
    try {
        const res = await fetchProtegido(`${API_URL}/alunos/`);
        const dados = await res.json();
        listaGlobalAlunos = dados;
        
        container.innerHTML = ""; // Limpa a lista

        if (dados.length === 0) {
            container.innerHTML = '<p class="col-span-full text-center py-10 text-slate-400">Nenhum aluno cadastrado.</p>';
            return;
        }

        dados.forEach(aluno => {
            // Criamos o HTML de cada card
            const cores = {
                'VIP': 'bg-emerald-100 text-emerald-700 border-emerald-200',
                'DUO': 'bg-indigo-100 text-indigo-700 border-indigo-200',
                'TEAM': 'bg-slate-100 text-slate-700 border-slate-200'
            };
            const classeCor = cores[aluno.tipo] || cores['TEAM'];

            const card = `
            <div class="p-4 border rounded-xl bg-white flex justify-between items-center shadow-sm hover:shadow-md transition">
                <div>
                    <div class="flex items-center gap-2 mb-1">
                        <p class="font-bold text-slate-800">${aluno.nome} ${aluno.sobrenome || ''}</p>
                        <span class="px-2 py-0.5 rounded-md text-[9px] font-black border ${classeCor}">
                            ${aluno.tipo || 'TEAM'}
                        </span>
                    </div>
                    <p class="text-[10px] text-slate-500">
                        <i class="fa-solid fa-phone"></i> ${aluno.telefone || 'Sem número'}
                    </p>
                </div>
                <div class="flex gap-3 items-center">
                    <button onclick="verRelatorio(${aluno.id}, '${aluno.nome}')" class="text-blue-500 hover:text-blue-700 transition-colors" title="Ver Relatório">
                        <i class="fa-solid fa-chart-line text-lg"></i>
                    </button>
                    
                    <button id="edit-${aluno.id}" class="text-indigo-500 hover:text-indigo-700">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button onclick="deletarAluno(${aluno.id})" class="text-slate-300 hover:text-red-500">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>`;
            
            container.innerHTML += card;

            // Atribuímos o clique de editar de forma manual para não dar erro de aspas
            setTimeout(() => {
                const btn = document.getElementById(`edit-${aluno.id}`);
                if(btn) btn.onclick = () => abrirModalEditarAluno(aluno);
            }, 50);
        });
    } catch (e) { 
        console.error("Erro ao carregar:", e); 
    }
}

async function adicionarAlunoNaTurma(turmaId) {
    // 1. Pergunta o ID do aluno (depois podemos evoluir para um <select>)
    const alunoId = prompt("Digite o ID do aluno que deseja adicionar a esta turma:");
    
    if (!alunoId) return; // Cancela se o usuário não digitar nada

    try {
        // 2. Faz a chamada para o seu backend
        // Note que usamos POST conforme o padrão de alteração de estado
        const response = await fetchProtegido(`/turmas/${turmaId}/adicionar-aluno?aluno_id=${alunoId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            Swal.fire('Sucesso!', 'Aluno adicionado à turma.', 'success');
            // 3. Chama a função que você já tem para atualizar a lista na tela
            if (typeof carregarTurmas === "function") {
                carregarTurmas(); 
            } else {
                location.reload();
            }
        } else {
            // Exibe o erro que o FastAPI retornar (ex: "Aluno não encontrado")
            Swal.fire('Erro', data.detail || 'Não foi possível adicionar o aluno', 'error');
        }
    } catch (error) {
        console.error("Erro na requisição:", error);
        alert("Erro técnico ao conectar com o servidor.");
    }
}

async function abrirModalAluno() {
    const { value: formValues } = await Swal.fire({
        title: 'Novo Aluno',
        html: `
            <div class="space-y-2">
                <input id="sw-nome" class="swal2-input-custom" placeholder="Nome *">
                <input id="sw-sobrenome" class="swal2-input-custom" placeholder="Sobrenome *">
                <input id="sw-telefone" class="swal2-input-custom" placeholder="Telefone (WhatsApp) *">
                <input id="sw-email" class="swal2-input-custom" placeholder="E-mail *">
                
                <div class="text-left mt-3">
                    <label class="text-[10px] font-bold text-slate-400 uppercase ml-1">Plano do Aluno</label>
                    <select id="sw-tipo" class="swal2-input-custom">
                        <option value="VIP">VIP (Pode cancelar/repor)</option>
                        <option value="TEAM">TEAM (Apenas visualiza)</option>
                        <option value="DUO">DUO (Apenas visualiza)</option>
                    </select>
                </div>

                <hr class="my-4 border-slate-100">
                <p class="text-[10px] font-bold text-slate-400 uppercase text-left">Opcional</p>
                <input id="sw-endereco" class="swal2-input-custom" placeholder="Endereço">
                <div class="grid grid-cols-2 gap-2">
                    <input id="sw-cidade" class="swal2-input-custom" placeholder="Cidade">
                    <input id="sw-estado" class="swal2-input-custom" placeholder="Estado (UF)">
                </div>
            </div>
        `,
        focusConfirm: false,
        preConfirm: () => {
            const dados = {
                nome: document.getElementById('sw-nome').value,
                sobrenome: document.getElementById('sw-sobrenome').value,
                telefone: document.getElementById('sw-telefone').value,
                email: document.getElementById('sw-email').value,
                tipo: document.getElementById('sw-tipo').value, // PEGA O VALOR DO SELECT AQUI
                endereco: document.getElementById('sw-endereco').value || null,
                cidade: document.getElementById('sw-cidade').value || null,
                estado: document.getElementById('sw-estado').value || null
            };

            if (!dados.nome || !dados.sobrenome || !dados.telefone || !dados.email) {
                return Swal.showValidationMessage('Nome, Sobrenome, Telefone e E-mail são obrigatórios');
            }
            return dados;
        }
    });

    if (formValues) {
        try {
            const res = await fetchProtegido(`${API_URL}/alunos/`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(formValues)
            });
            
            if(res.ok) { 
                Toast.fire({icon: 'success', title: 'Aluno cadastrado com sucesso!'}); 
                carregarAlunos(); 
            } else {
                const erroDetalhado = await res.json();
                console.error("Erro do Servidor:", erroDetalhado);
                Swal.fire('Erro 422', 'O servidor rejeitou os campos. Verifique o console (F12) para detalhes.', 'error');
            }
        } catch (e) {
            Swal.fire('Erro', 'Não foi possível conectar ao servidor.', 'error');
        }
    }
}

async function deletarAluno(id) {
    Swal.fire({
        title: 'Tem certeza?',
        text: "Isso excluirá o aluno permanentemente!",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#3085d6',
        cancelButtonColor: '#d33',
        confirmButtonText: 'Sim, deletar!'
    }).then(async (result) => {
        if (result.isConfirmed) {
            await fetchProtegido(`${API_URL}/alunos/${id}`, { method: 'DELETE' });
            carregarAlunos();
            Toast.fire({icon: 'success', title: 'Excluído!'});
        }
    });
}

// --- GESTÃO DE TURMAS ---
async function carregarTurmas() {
    const container = document.getElementById('listaTurmas');
    try {
        const res = await fetchProtegido(`${API_URL}/turmas/`);
        const turmas = await res.json();
        
        container.innerHTML = ""; 

        if (turmas.length === 0) {
            container.innerHTML = '<p class="col-span-full text-center py-10 text-slate-400">Nenhuma turma criada.</p>';
            return;
        }

        const limites = { "VIP": 1, "DUO": 2, "TEAM": 6 };

        turmas.forEach(t => {
            const limiteMax = limites[t.tipo] || 6;
            const totalAlunos = t.alunos.length;
            const estaCheia = totalAlunos >= limiteMax;

            container.innerHTML += `
            <div class="p-5 border rounded-2xl bg-white shadow-sm border-t-4 ${estaCheia ? 'border-red-500' : 'border-purple-500'}">
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h3 class="font-black text-slate-800 text-lg">${t.nome_turma}</h3>
                        <span class="text-[10px] bg-purple-50 text-purple-600 px-2 py-1 rounded-full font-bold">${t.tipo}</span>
                    </div>
                    <span class="text-xs ${estaCheia ? 'text-red-600 font-bold' : 'text-slate-400'}">
                        <i class="fa-solid fa-user-group"></i> ${totalAlunos}/${limiteMax}
                    </span>
                </div>

                <div class="space-y-2 mb-4">
                    ${t.alunos.map(al => `
                        <div class="flex justify-between items-center bg-slate-50 p-2 rounded-lg border border-slate-100 group">
                            <span class="text-sm text-slate-700">${al.nome}</span>
                            <button onclick="removerAluno(${t.id}, ${al.id})" class="text-slate-300 hover:text-red-500 transition">
                                <i class="fa-solid fa-circle-xmark"></i>
                            </button>
                        </div>
                    `).join('')}
                </div>

                <div id="area-adicao-${t.id}" class="hidden mb-4 p-3 bg-indigo-50 rounded-xl border border-indigo-100 space-y-2">
                    <label class="text-[9px] font-black text-indigo-400 uppercase tracking-widest">Selecionar Aluno Livre</label>
                    <select id="select-alunos-livres-${t.id}" class="w-full bg-white border border-indigo-200 rounded-lg px-2 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-indigo-500">
                        <option value="">Carregando...</option>
                    </select>
                    <div class="flex gap-2">
                        <button onclick="confirmarAdicao(${t.id})" class="flex-1 bg-indigo-600 text-white py-2 rounded-lg text-[10px] font-bold uppercase hover:bg-indigo-700 transition shadow-md shadow-indigo-100">
                            Confirmar
                        </button>
                        <button onclick="document.getElementById('area-adicao-${t.id}').classList.add('hidden')" class="bg-white text-slate-400 px-3 rounded-lg text-[10px] font-bold uppercase border border-slate-200">
                            X
                        </button>
                    </div>
                </div>

                <div class="flex gap-2 border-t pt-4">
                    <button onclick="prepararAdicao(${t.id}, '${t.tipo}', ${totalAlunos}, ${limiteMax})" 
                        ${estaCheia ? 'disabled' : ''}
                        class="flex-1 text-[10px] font-bold uppercase p-2 rounded-lg ${estaCheia ? 'bg-slate-100 text-slate-300 cursor-not-allowed' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-600 hover:text-white'} transition">
                        <i class="fa-solid fa-plus"></i> Aluno
                    </button>
                    <button onclick="deletarTurma(${t.id})" class="p-2 text-slate-300 hover:text-red-500 transition">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>`;
        });
    } catch (e) { 
        console.error("Erro ao carregar turmas", e);
        container.innerHTML = '<p class="text-center text-red-500">Erro ao carregar turmas.</p>';
    }
}

async function abrirModalTurma() {
    // 1. Buscamos os alunos (Corrigido o nome da variável para não dar erro)
    const resposta = await fetchProtegido(`${API_URL}/alunos/`);
    const todosAlunos = await resposta.json();
    const alunosLivres = todosAlunos.filter(a => !a.turma_id);

    let listaAlunosHTML = alunosLivres.map(al => `
        <label class="flex items-center gap-2 p-2 hover:bg-slate-50 rounded-lg cursor-pointer border border-slate-100">
            <input type="checkbox" name="aluno-turma" value="${al.id}" class="rounded text-indigo-600">
            <span class="text-sm text-slate-700">${al.nome} ${al.sobrenome || ''}</span>
        </label>
    `).join('');

    // Variável temporária para os horários
    let horariosDestaTurma = [];

    const { value: formValues } = await Swal.fire({
        title: 'Criar Nova Turma',
        html: `
            <div class="text-left space-y-4">
                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Nome do Grupo</label>
                    <input id="t-nome" class="swal2-input-custom" placeholder="Ex: Duo de Quinta">
                </div>
                
                <div class="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <label class="text-[10px] font-bold uppercase text-slate-400 mb-2 block text-indigo-600">Configurar Horários</label>
                    <div class="flex gap-2 mb-3">
                        <select id="t-dia-add" class="text-xs p-2 rounded-lg border flex-1 outline-none">
                            <option value="0">Segunda</option>
                            <option value="1">Terça</option>
                            <option value="2">Quarta</option>
                            <option value="3">Quinta</option>
                            <option value="4">Sexta</option>
                        </select>
                        <input type="time" id="t-hora-add" class="text-xs p-2 rounded-lg border w-24 outline-none">
                        <button type="button" id="btn-add-hora" class="bg-indigo-600 text-white px-4 rounded-lg font-black hover:bg-indigo-700 transition">+</button>
                    </div>
                    <div id="lista-horarios-temp" class="space-y-1"></div>
                </div>

                <div class="mt-4">
                    <label class="block text-left text-[10px] font-bold uppercase text-slate-400 mb-1">Duração da Aula</label>
                    <select id="t-duracao" class="w-full p-2 border rounded-lg text-sm bg-slate-50">
                        <option value="45">45 minutos</option>
                        <option value="60" selected>1 hora (Padrão)</option>
                        <option value="90">1 hora e 30 min</option>
                        <option value="120">2 horas</option>
                    </select>
                </div>

                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Modalidade</label>
                    <select id="t-tipo" class="swal2-input-custom">
                        <option value="TEAM">TEAM (até 6)</option>
                        <option value="DUO">DUO (2 alunos)</option>
                    </select>
                </div>

                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Selecionar Alunos</label>
                    <div class="max-h-32 overflow-y-auto mt-2 space-y-1 p-1 border rounded-lg bg-white">
                        ${listaAlunosHTML || '<p class="text-[10px] text-slate-400 p-2">Nenhum aluno livre disponível.</p>'}
                    </div>
                </div>
            </div>
        `,
        didOpen: () => {
            const btnAdd = document.getElementById('btn-add-hora');
            const containerLista = document.getElementById('lista-horarios-temp');

            btnAdd.onclick = () => {
                const diaSelect = document.getElementById('t-dia-add');
                const horaInput = document.getElementById('t-hora-add');
                
                if(!horaInput.value) {
                    Toast.fire({ icon: 'warning', title: 'Informe a hora!' });
                    return;
                }
                
                const novoHorario = { 
                    dia: parseInt(diaSelect.value), 
                    hora: horaInput.value 
                };

                horariosDestaTurma.push(novoHorario);
                
                // Atualiza a visualização
                const nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
                containerLista.innerHTML = horariosDestaTurma.map((h, i) => `
                    <div class="flex justify-between items-center bg-white p-2 rounded-lg border border-indigo-100 text-[10px] font-black text-indigo-600 shadow-sm animate-in fade-in zoom-in duration-200">
                        <span><i class="fa-regular fa-clock mr-1"></i> ${nomes[h.dia]} às ${h.hora}</span>
                        <button type="button" class="text-red-400 hover:text-red-600 p-1" onclick="this.closest('div').remove();">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                `).join('');
            };
        },
        preConfirm: () => {
            const nome = document.getElementById('t-nome').value;
            const tipo = document.getElementById('t-tipo').value;
            const selecionados = Array.from(document.querySelectorAll('input[name="aluno-turma"]:checked')).map(el => Number(el.value));

            if (!nome || horariosDestaTurma.length === 0) {
                return Swal.showValidationMessage('Preencha o nome e adicione pelo menos um horário no botão "+"');
            }
            if (selecionados.length === 0) {
                return Swal.showValidationMessage('Selecione pelo menos um aluno');
            }

            return { 
                nome_turma: nome,
                tipo: tipo,
                duracao_minutos: document.getElementById('t-duracao').value,
                horarios: horariosDestaTurma,
                aluno_ids: selecionados 
            };
        }
    });

    if (formValues) {
        try {
            const res = await fetchProtegido(`${API_URL}/turmas/`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(formValues)
            });
            if (res.ok) { 
                carregarTurmas(); 
                Toast.fire({icon:'success', title:'Turma e horários criados!'}); 
            } else {
                const erro = await res.json();
                Swal.fire('Erro', erro.detail || 'Erro ao criar turma', 'error');
            }
        } catch (e) {
            console.error(e);
        }
    }
}

async function deletarTurma(id) {
    const confirmar = await Swal.fire({
        title: 'Excluir Turma?',
        text: "Os alunos ficarão sem turma, mas não serão deletados.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Sim, excluir',
        cancelButtonText: 'Cancelar'
    });

    if (confirmar.isConfirmed) {
        const res = await fetchProtegido(`${API_URL}/turmas/${id}`, { method: 'DELETE' });
        if (res.ok) {
            Toast.fire({icon: 'success', title: 'Turma removida'});
            carregarTurmas();
        }
    }
}

// --- AGENDA ---
async function carregarAgenda() {
    const container = document.getElementById('listaAgenda');
    try {
        const res = await fetchProtegido(`${API_URL}/aulas/lista-professor`);
        const aulas = await res.json();
        if (!Array.isArray(aulas)) {
            console.error("O servidor não retornou uma lista. Verifique o login.");
            return; // Para aqui e não tenta dar o forEach
        }
        
        container.innerHTML = aulas.length ? '' : '<p class="col-span-full text-slate-400 py-10 text-center">Nenhuma aula agendada.</p>';
        
        const agora = new Date();

        // Usamos o index (i) para identificar qual objeto da lista estamos clicando
        aulas.forEach((a, i) => {
            const dataAula = new Date(a.data_inicio);
            const podeDarPresenca = agora >= dataAula;
            const dataFormatada = dataAula.toLocaleDateString('pt-BR', { 
                weekday: 'short', day: '2-digit', month: 'long' 
            });

            // Definimos a cor do status (usando o status do primeiro aluno como base)
            const statusCor = a.status === 'presente' ? 'border-green-500' : 'border-indigo-500';

            container.innerHTML += `
                <div class="p-5 border rounded-2xl bg-white shadow-sm border-l-8 ${statusCor} flex justify-between items-center hover:shadow-md transition-all">
                    <div class="flex-1">
                        <div class="flex items-center gap-2">
                            <p class="font-extrabold text-slate-900 text-lg leading-tight tracking-tight">
                                ${a.nome_exibicao} 
                            </p>
                            <span class="text-[9px] font-black px-2 py-0.5 rounded bg-indigo-50 text-indigo-600 border border-indigo-100 uppercase">
                                ${a.tipo} ${a.is_turma ? `(${a.alunos.length})` : ''}
                            </span>
                        </div>

                        <div class="mt-4 flex flex-wrap items-center gap-2">
                            <p class="text-[11px] text-slate-600 font-bold bg-slate-50 px-2 py-1 rounded-md border border-slate-100">
                                <i class="fa-regular fa-calendar text-indigo-500 mr-1"></i> 
                                ${dataFormatada}
                            </p>
                            <p class="text-[11px] text-slate-600 font-bold bg-slate-50 px-2 py-1 rounded-md border border-slate-100">
                                <i class="fa-regular fa-clock text-indigo-500 mr-1"></i> 
                                ${dataAula.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                            </p>
                        </div>
                    </div>

                    <div class="flex items-center gap-3 ml-4">
                        <button id="btn-chamada-${i}"
                                ${podeDarPresenca ? '' : 'disabled'}
                                class="${podeDarPresenca 
                                    ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-100' 
                                    : 'bg-slate-100 text-slate-400 cursor-not-allowed border-slate-200'} 
                                    p-4 rounded-2xl transition-all active:scale-95 flex flex-col items-center gap-1"
                                title="${podeDarPresenca ? 'Fazer Chamada' : 'Aguarde o horário da aula'}">
                            <i class="fa-solid fa-clipboard-user text-xl"></i>
                            <span class="text-[8px] font-black uppercase">${podeDarPresenca ? 'Chamada' : 'Bloqueado'}</span>
                        </button>

                        <button id="btn-cancelar-${i}" 
                                class="text-slate-300 hover:text-red-500 p-2 transition-colors hover:bg-red-50 rounded-full"
                                title="Cancelar Aula da Turma">
                            <i class="fa-solid fa-circle-xmark text-lg"></i>
                        </button>
                    </div>
                </div>`;

            // Atribuímos o evento de clique após criar o HTML para evitar erro de aspas no JSON
            setTimeout(() => {
                const btnCancel = document.getElementById(`btn-cancelar-${i}`);
                if(btnCancel) btnCancel.onclick = () => cancelarAulaGrupo(a);
                const btn = document.getElementById(`btn-chamada-${i}`);
                if(btn) btn.onclick = () => abrirChamadaRetroativa(a, false);
            }, 0);
        });
    } catch (e) { console.error("Erro na agenda", e); }
}

// FUNÇÃO QUE ABRE O POPUP DE CHAMADA E NOTA
// ==========================================
// PORTAS DE ENTRADA (Nomes que seu código já usa)
// ==========================================

async function abrirChamada(dados) {
    await abrirLogicaUniversal(dados, false);
}

async function abrirChamadaRetroativa(dados, ehRetroativa) {
    await abrirLogicaUniversal(dados, ehRetroativa);
}

async function abrirChamadaRetroativaGrupo(nomeExibicao, alunosJSON) {
    try {
        // Converte a string de alunos de volta para objeto
        const alunos = typeof alunosJSON === 'string' ? JSON.parse(alunosJSON) : alunosJSON;
        
        // Monta o objeto no formato que a Lógica Universal espera
        const dadosFormatados = {
            nome_exibicao: nomeExibicao,
            alunos: alunos
        };
        
        await abrirLogicaUniversal(dadosFormatados, true);
    } catch (e) {
        console.error("Erro ao abrir chamada do histórico:", e);
        Swal.fire("Erro", "Não foi possível carregar os alunos desta sessão.", "error");
    }
}

// ==========================================
// CÉREBRO UNIFICADO (Usando o seu HTML que funciona)
// ==========================================
async function abrirLogicaUniversal(dadosAgrupados, ehRetroativa) {
    let dados;
    try {
        dados = typeof dadosAgrupados === 'string' ? JSON.parse(dadosAgrupados) : dadosAgrupados;
    } catch (e) {
        console.error("Erro nos dados:", e);
        return;
    }

    const listaAlunos = dados.alunos;
    const base = listaAlunos[0];
    
    // Pegamos o desempenho do banco (ex: "Bom", "Médio", "Ruim")
    const notaBanco = base.desempenho || "";

    const listaAlunosHtml = listaAlunos.map(al => {
        const idUnico = ehRetroativa ? al.historico_id : al.aula_id;
        const statusPresente = ehRetroativa ? al.status_presenca : (al.status === 'presente');
        
        return `
            <div class="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100 mb-2">
                <span class="font-bold text-slate-700 text-sm">${al.nome}</span>
                <select id="status-${idUnico}" class="border-2 border-slate-200 rounded-lg p-1 text-xs font-bold outline-none focus:border-indigo-500">
                    <option value="presente" ${statusPresente ? 'selected' : ''}>✅ Presente</option>
                    <option value="ausente" ${!statusPresente ? 'selected' : ''}>❌ Ausente</option>
                </select>
            </div>
        `;
    }).join('');

    const { value: formValues } = await Swal.fire({
        title: `<div class="flex flex-col items-center gap-1">
                    <span class="text-[10px] uppercase text-slate-400 font-black tracking-widest">${ehRetroativa ? 'Chamada Retroativa' : 'Chamada de Aula'}</span>
                    <span class="text-indigo-900 font-black text-xl italic">${dados.nome_exibicao}</span>
                </div>`,
        html: `
            <div class="text-left space-y-4 p-2">
                <div class="max-h-48 overflow-y-auto pr-1">${listaAlunosHtml}</div>
                
                <label class="block text-[10px] font-bold uppercase text-slate-400 tracking-wider">Desempenho</label>
                <div class="grid grid-cols-3 gap-3">
                    
                    <label class="cursor-pointer">
                        <input type="radio" name="nota" value="Ruim" class="peer hidden" ${notaBanco === 'Ruim' ? 'checked' : ''}>
                        <div class="text-center p-3 border-2 border-slate-100 rounded-xl transition-all peer-checked:bg-red-50 peer-checked:border-red-500 peer-checked:scale-95">
                            <div class="text-xl mb-1">🙁</div>
                            <div class="text-[10px] font-bold text-slate-600 uppercase">Ruim</div>
                        </div>
                    </label>

                    <label class="cursor-pointer">
                        <input type="radio" name="nota" value="Médio" class="peer hidden" ${notaBanco === 'Médio' ? 'checked' : ''}>
                        <div class="text-center p-3 border-2 border-slate-100 rounded-xl transition-all peer-checked:bg-yellow-50 peer-checked:border-yellow-500 peer-checked:scale-95">
                            <div class="text-xl mb-1">😐</div>
                            <div class="text-[10px] font-bold text-slate-600 uppercase">Médio</div>
                        </div>
                    </label>

                    <label class="cursor-pointer">
                        <input type="radio" name="nota" value="Bom" class="peer hidden" ${(!notaBanco || notaBanco === 'Bom') ? 'checked' : ''}>
                        <div class="text-center p-3 border-2 border-slate-100 rounded-xl transition-all peer-checked:bg-green-50 peer-checked:border-green-500 peer-checked:scale-95">
                            <div class="text-xl mb-1">🤩</div>
                            <div class="text-[10px] font-bold text-slate-600 uppercase">Bom</div>
                        </div>
                    </label>

                </div>

                <label class="block text-[10px] font-bold uppercase text-slate-400 tracking-wider">Conteúdo / Obs</label>
                <textarea id="ch-obs-universal" class="w-full border-2 border-slate-100 rounded-xl p-3 text-sm h-24 focus:border-indigo-500 outline-none">${base.observacao || ''}</textarea>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Salvar Registro',
        confirmButtonColor: '#4f46e5',
        preConfirm: () => {
            return listaAlunos.map(al => {
                const idUnico = ehRetroativa ? al.historico_id : al.aula_id;
                return {
                    id: idUnico,
                    status: document.getElementById(`status-${idUnico}`).value,
                    desempenho: document.querySelector('input[name="nota"]:checked').value,
                    observacao: document.getElementById('ch-obs-universal').value
                };
            });
        }
    });

    if (formValues) {
        for (const item of formValues) {
            const params = new URLSearchParams({ status: item.status, desempenho: item.desempenho, observacao: item.observacao });
            const rota = ehRetroativa ? `/aulas/admin/presenca-retroativa/${item.id}` : `/aulas/${item.id}/presenca`;
            await fetchProtegido(`${API_URL}${rota}?${params.toString()}`, { method: 'PATCH' });
        }
        Toast.fire({ icon: 'success', title: 'Registro atualizado!' });
        if (ehRetroativa) carregarHistoricoGeral(); else carregarAgenda();
    }
}

async function cancelarAula(id) {
    if(confirm("Deseja cancelar esta aula?")) {
        await fetchProtegido(`${API_URL}/aulas/${id}`, { method: 'DELETE' });
        carregarAgenda();
    }
}

// --- GRADE BASE E CALENDÁRIO ---
// --- MODIFICAÇÃO NA FUNÇÃO DE GERAR CALENDÁRIO ---
function gerarCalendario() {
    const grid = document.getElementById('calendarioMensal');
    const labelMes = document.getElementById('mesAtualExtenso');
    if(!grid) return;

    grid.innerHTML = ['Dom','Seg','Ter','Qua','Qui','Sex','Sab'].map(d => 
        `<div class="bg-slate-50 p-2 text-center text-[10px] font-black text-slate-400 uppercase">${d}</div>`
    ).join('');
    
    const ano = dataAtualCalendario.getFullYear();
    const mes = dataAtualCalendario.getMonth();
    labelMes.innerText = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(dataAtualCalendario);

    const primeiroDia = new Date(ano, mes, 1).getDay();
    const ultimoDia = new Date(ano, mes + 1, 0).getDate();

    for (let i = 0; i < primeiroDia; i++) grid.innerHTML += `<div class="bg-slate-50/50 h-24 border border-slate-100/50"></div>`;
    
    for (let dia = 1; dia <= ultimoDia; dia++) {
        const ehHoje = (new Date()).toDateString() === (new Date(ano, mes, dia)).toDateString();
        // ADICIONADO: id="dia-container-${dia}" para podermos inserir as aulas depois
        grid.innerHTML += `
            <div onclick="selecionarDia(this, ${dia}, ${new Date(ano,mes,dia).getDay()})" 
                 class="bg-white h-24 p-1 border border-slate-100 hover:border-indigo-500 cursor-pointer transition-colors relative overflow-y-auto">
                <span class="text-[10px] font-black ${ehHoje ? 'bg-indigo-600 text-white w-5 h-5 flex items-center justify-center rounded-full' : 'text-slate-300'}">
                    ${dia}
                </span>
                <div id="eventos-dia-${dia}" class="flex flex-col gap-1 mt-1"></div>
            </div>`;
    }

    // CHAMADA NOVA: Assim que termina de desenhar o calendário, busca as aulas
    renderizarAulasNoCalendario(mes, ano);
}

// --- FUNÇÃO NOVA PARA PREENCHER O CALENDÁRIO ---
async function renderizarAulasNoCalendario(mesAtual, anoAtual) {
    try {
        // Busca todas as sessões do histórico que você já tem no backend
        const res = await fetchProtegido(`${API_URL}/aulas/admin/historico-geral`);
        const sessoes = await res.json();

        sessoes.forEach(sessao => {
            // A data que vem do backend (sessao.data) costuma ser YYYY-MM-DD
            const dataAula = new Date(sessao.data + "T00:00:00"); // Força fuso local
            
            // Verifica se a aula pertence ao mês e ano que o professor está vendo
            if (dataAula.getMonth() === mesAtual && dataAula.getFullYear() === anoAtual) {
                const dia = dataAula.getDate();
                const container = document.getElementById(`eventos-dia-${dia}`);
                
                if (container) {
                    // Adiciona uma pequena "pílula" visual para cada aula
                    const pill = document.createElement('div');
                    pill.className = "text-[7px] px-1 py-0.5 bg-indigo-50 text-indigo-700 rounded border border-indigo-100 truncate font-black uppercase tracking-tighter";
                    pill.innerText = sessao.nome_exibicao;
                    pill.title = sessao.nome_exibicao; // Mostra nome completo ao passar o mouse
                    container.appendChild(pill);
                }
            }
        });
    } catch (e) {
        console.error("Erro ao carregar aulas no calendário:", e);
    }
}

function selecionarDia(el, dia, diaSemana) {
    document.querySelectorAll('.dia-selecionado').forEach(d => d.classList.remove('dia-selecionado'));
    el.classList.add('dia-selecionado');
    // Ajuste para o Python (0=Segunda... 6=Domingo)
    const diaAjustado = diaSemana === 0 ? 6 : diaSemana - 1;
    document.getElementById('diaSemanaOculto').value = diaAjustado;
    document.getElementById('tituloDiaSelecionado').innerText = `Configurar ${diasNome[diaAjustado]}`;
}

async function carregarTudoGrade() {
    gerarCalendario();
    carregarGridSemanal();
}

async function carregarGridSemanal() {
    try {
        const res = await fetchProtegido(`${API_URL}/aulas/grade`);
        const grade = await res.json();
        const container = document.getElementById('gridSemanal');
        container.innerHTML = '';
        
        diasNome.forEach((nome, i) => {
            const turnos = grade.filter(g => g.dia_semana == i);
            if(turnos.length) {
                container.innerHTML += `
                    <div class="mb-4">
                        <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest">${nome}</p>
                        ${turnos.map(t => `
                            <div class="text-[10px] bg-slate-50 p-2 rounded-lg mb-1 flex justify-between items-center border border-slate-100">
                                <span class="font-bold text-slate-700">${t.hora_inicio} - ${t.hora_fim}</span>
                                <button onclick="deletarTurno(${t.id})" class="text-red-400 hover:text-red-600 transition">
                                    <i class="fa-solid fa-trash"></i>
                                </button>
                            </div>
                        `).join('')}
                    </div>`;
            }
        });
    } catch (e) {}
}

async function deletarTurno(id) {
    await fetchProtegido(`${API_URL}/aulas/grade/${id}`, { method: 'DELETE' });
    carregarGridSemanal();
}

document.getElementById('formGrade').onsubmit = async (e) => {
    e.preventDefault();
    const dia = document.getElementById('diaSemanaOculto').value;
    const inicio = document.getElementById('inicioGrade').value;
    const fim = document.getElementById('fimGrade').value;
    if(dia === "") return Toast.fire({icon:'warning', title:'Selecione um dia no calendário'});
    
    await fetchProtegido(`${API_URL}/aulas/configurar-grade?dia=${dia}&inicio=${inicio}&fim=${fim}`, {method: 'POST'});
    Toast.fire({icon: 'success', title: 'Horário salvo!'});
    carregarTudoGrade();
};

function mudarMes(d) {
    dataAtualCalendario.setMonth(dataAtualCalendario.getMonth() + d);
    gerarCalendario();
}

// Inicialização
window.onload = () => {
    const token = localStorage.getItem('token_professor');
    const estaNoPainel = document.getElementById('listaAgenda'); 

    // 1. Só tenta carregar dados se o elemento da agenda existir (ou seja, se estiver no painel)
    if (estaNoPainel) {
        if (token) {
            carregarAgenda();
            // Você também pode chamar as outras aqui para garantir
            carregarAlunos();
            carregarTurmas();
        } else {
            // 2. Se cair no painel sem token, expulsa para o login
            window.location.href = "/frontend/login.html";
        }
    }
    // 3. Se estiver na página de login, o código acima é ignorado e não gera erro 401
};

async function abrirModalEditarAluno(aluno) {
    const { value: formValues } = await Swal.fire({
        title: 'Editar Aluno',
        html: `
            <div class="space-y-2">
                <input id="ed-nome" class="swal2-input-custom" placeholder="Nome" value="${aluno.nome}">
                <input id="ed-sobrenome" class="swal2-input-custom" placeholder="Sobrenome" value="${aluno.sobrenome || ''}">
                <input id="ed-telefone" class="swal2-input-custom" placeholder="Telefone" value="${aluno.telefone}">
                <input id="ed-email" class="swal2-input-custom" placeholder="E-mail" value="${aluno.email}">
                <select id="ed-tipo" class="swal2-input-custom">
                    <option value="VIP" ${aluno.tipo === 'VIP' ? 'selected' : ''}>VIP</option>
                    <option value="DUO" ${aluno.tipo === 'DUO' ? 'selected' : ''}>DUO</option>
                    <option value="TEAM" ${aluno.tipo === 'TEAM' ? 'selected' : ''}>TEAM</option>
                </select>
                <hr class="my-4">
                <input id="ed-endereco" class="swal2-input-custom" placeholder="Endereço" value="${aluno.endereco || ''}">
                <div class="grid grid-cols-2 gap-2">
                    <input id="ed-cidade" class="swal2-input-custom" placeholder="Cidade" value="${aluno.cidade || ''}">
                    <input id="ed-estado" class="swal2-input-custom" placeholder="Estado" value="${aluno.estado || ''}">
                </div>
            </div>
        `,
        focusConfirm: false,
        preConfirm: () => {
            return {
                nome: document.getElementById('ed-nome').value,
                sobrenome: document.getElementById('ed-sobrenome').value,
                telefone: document.getElementById('ed-telefone').value,
                email: document.getElementById('ed-email').value,
                tipo: document.getElementById('ed-tipo').value,
                endereco: document.getElementById('ed-endereco').value || null,
                cidade: document.getElementById('ed-cidade').value || null,
                estado: document.getElementById('ed-estado').value || null
            }
        }
    });

    if (formValues) {
        const res = await fetchProtegido(`${API_URL}/alunos/${aluno.id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(formValues)
        });

        if (res.ok) {
            Toast.fire({ icon: 'success', title: 'Aluno atualizado!' });
            carregarAlunos();
        } else {
            Swal.fire('Erro', 'Não foi possível atualizar o aluno.', 'error');
        }
    }
}

async function abrirModalAdicao(turmaId, tipoTurma) {
    // 1. Busca alunos sem turma no backend
    const response = await fetchProtegido('/alunos/sem-turma');
    const alunosLivres = await response.json();

    const select = document.getElementById(`select-alunos-livres-${turmaId}`);
    select.innerHTML = '<option value="">Selecione um aluno...</option>';

    alunosLivres.forEach(aluno => {
        select.innerHTML += `<option value="${aluno.id}">${aluno.nome} ${aluno.sobrenome}</option>`;
    });

    // 2. Mostra o container
    document.getElementById(`container-adicao-${turmaId}`).style.display = 'block';
}

async function gerarAulasDoMes() {
    const confirmacao = await Swal.fire({
        title: 'Gerar agenda do mês?',
        text: "O sistema criará automaticamente todas as aulas deste mês baseadas nos horários fixos das turmas e enviará para o Google Agenda.",
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#10b981', // Cor emerald
        confirmButtonText: 'Sim, gerar agora!',
        cancelButtonText: 'Cancelar'
    });

    if (confirmacao.isConfirmed) {
        // Mostra o "carregando" (importante porque o Google Agenda demora uns segundos para responder)
        Swal.fire({ 
            title: 'Sincronizando com Google...', 
            allowOutsideClick: false, 
            didOpen: () => { Swal.showLoading(); } 
        });

        try {
            const res = await fetchProtegido(`${API_URL}/turmas/gerar-mensal`, { method: 'POST' });
            const dados = await res.json();

            if (res.ok) {
                Swal.fire('Sucesso!', 'Histórico e Google Agenda atualizados para os próximos 30 dias!', 'success');
                
                // Recarrega as listas para as aulas novas aparecerem na tela
                if (typeof carregarHistoricoGeral === "function") carregarHistoricoGeral();
                if (typeof carregarAgenda === "function") carregarAgenda();
            } else {
                Swal.fire('Erro', dados.detail || 'Erro ao gerar aulas', 'error');
            }
        } catch (e) {
            Swal.fire('Erro', 'Não foi possível conectar ao servidor.', 'error');
        }
    }
}

async function abrirModalAgendamentoAvulso() {
    // 1. Buscamos todos os alunos para preencher o select
    const res = await fetchProtegido(`${API_URL}/alunos/`);
    const alunos = await res.json();

    const optionsAlunos = alunos.map(al => 
        `<option value="${al.id}">${al.nome} ${al.sobrenome || ''} (${al.tipo})</option>`
    ).join('');

    const { value: formValues } = await Swal.fire({
        title: 'Agendar Aula Individual',
        html: `
            <div class="text-left space-y-4">
                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Selecionar Aluno</label>
                    <select id="avulso-aluno" class="swal2-input-custom">
                        ${optionsAlunos}
                    </select>
                </div>
                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Data e Hora de Início</label>
                    <input id="avulso-data" type="datetime-local" class="swal2-input-custom">
                </div>
            </div>
        `,
        focusConfirm: false,
        preConfirm: () => {
            return {
                aluno_id: document.getElementById('avulso-aluno').value,
                data_inicio: document.getElementById('avulso-data').value
            }
        }
    });

    if (formValues) {
        enviarAgendamentoAvulso(formValues);
    }
}

async function enviarAgendamentoAvulso(dados) {
    try {
        const res = await fetchProtegido(`${API_URL}/aulas/avulsa`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        if (res.ok) {
            const resposta = await res.json();
            
            // Verifica se o Google Calendar falhou (conforme mudamos no Python)
            if (resposta.google_sync === false) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Aula agendada!',
                    text: 'A aula foi salva, mas houve uma falha na sincronização com o Google Agenda. O professor precisará verificar manualmente.',
                    confirmButtonColor: '#f59e0b'
                });
            } else {
                Toast.fire({ icon: 'success', title: 'Aula agendada com sucesso!' });
            }
            
            carregarAgenda(); // Atualiza a lista de aulas
        } else {
            const erro = await res.json();
            Swal.fire('Erro', erro.detail || 'Erro ao agendar aula', 'error');
        }
    } catch (e) {
        Swal.fire('Erro', 'Falha na conexão com o servidor', 'error');
    }
}

async function salvarEdicaoAluno(id) {
    const dados = {
        nome: document.getElementById('editNome').value,
        tipo: document.getElementById('editTipo').value, // Verifique se esse valor é "DUO", "TEAM" ou "VIP"
        // ... outros campos
    };

    console.log("Dados que estou enviando:", dados); // VEJA ISSO NO F12 DO NAVEGADOR

    const res = await fetchProtegido(`/alunos/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados)
    });
    // ... restando da função
}

async function prepararAdicao(turmaId, tipoTurma, totalAlunos, limiteMax) {
    if (totalAlunos >= limiteMax) {
        return Swal.fire("Turma Cheia", `Esta turma ${tipoTurma} já atingiu o limite de ${limiteMax} alunos.`, "warning");
    }

    const area = document.getElementById(`area-adicao-${turmaId}`);
    const select = document.getElementById(`select-alunos-livres-${turmaId}`);
    
    // Mostra a área
    area.classList.remove('hidden');
    
    try {
        // Busca alunos que não estão em nenhuma turma
        const res = await fetchProtegido(`${API_URL}/alunos/`);
        const todosAlunos = await res.json();
        
        // Filtra alunos que NÃO têm turma_id ou que o turma_id seja null
        const alunosLivres = todosAlunos.filter(a => !a.turma_id);

        select.innerHTML = '<option value="">Selecione um aluno...</option>';
        
        if (alunosLivres.length === 0) {
            select.innerHTML = '<option value="">Nenhum aluno livre encontrado</option>';
            return;
        }

        alunosLivres.forEach(al => {
            select.innerHTML += `<option value="${al.id}">${al.nome} ${al.sobrenome || ''}</option>`;
        });
    } catch (e) {
        console.error("Erro ao buscar alunos livres", e);
        select.innerHTML = '<option value="">Erro ao carregar lista</option>';
    }
}

async function confirmarAdicao(turmaId) {
    const seletor = document.getElementById(`select-alunos-livres-${turmaId}`);
    const alunoId = seletor.value;

    console.log("--- INICIANDO ADIÇÃO ---");
    console.log("ID do Aluno:", alunoId);
    console.log("ID da Turma:", turmaId);

    if (!alunoId) return Swal.fire("Atenção", "Selecione um aluno!", "warning");

    try {
        const res = await fetchProtegido(`${API_URL}/turmas/${turmaId}/adicionar-aluno/${alunoId}`, {
            method: 'POST'
        });

        if (res.ok) {
            await Swal.fire("Sucesso!", "Aluno adicionado.", "success");
            // Em vez de carregar tudo, vamos apenas recarregar a página para limpar o estado
            window.location.reload(); 
        } else {
            const erro = await res.json();
            Swal.fire("Erro", erro.detail || "Falha ao adicionar", "error");
        }
    } catch (e) {
        console.error(e);
    }
}

async function verHistorico(alunoId, alunoNome) {
    try {
        const res = await fetchProtegido(`${API_URL}/aulas/historico/${alunoId}`);
        const dados = await res.json();

        let conteudoHtml = '';

        if (dados.length === 0) {
            conteudoHtml = `<p class="text-slate-500 py-4 text-center">Este aluno ainda não possui registros de presença.</p>`;
        } else {
            conteudoHtml = `
                <div class="overflow-x-auto mt-4">
                    <table class="w-full text-left border-collapse text-sm">
                        <thead>
                            <tr class="border-b bg-slate-50 text-slate-400 uppercase text-[10px] font-bold">
                                <th class="p-2">Data</th>
                                <th class="p-2 text-center">Status</th>
                                <th class="p-2 text-center">Nota</th>
                                <th class="p-2">Obs</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${dados.map(h => {
                                // Lógica de cores para a Nota
                                const corNota = h.desempenho === 'Bom' ? 'text-green-600' : 
                                               (h.desempenho === 'Médio' ? 'text-yellow-600' : 
                                               (h.desempenho === 'Ruim' ? 'text-red-600' : 'text-blue-600'));
                                
                                // Lógica de cores para o Status (ajustado para minúsculo/maiúsculo)
                                const statusBaixa = h.status.toLowerCase();
                                const classeStatus = statusBaixa === 'presente' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700';

                                return `
                                <tr class="border-b hover:bg-slate-50 transition-colors">
                                    <td class="p-2 font-medium text-slate-700">${new Date(h.data_inicio).toLocaleDateString('pt-BR')}</td>
                                    <td class="p-2 text-center">
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${classeStatus}">
                                            ${h.status.toUpperCase()}
                                        </span>
                                    </td>
                                    <td class="p-2 text-center font-bold ${corNota}">${h.desempenho || '-'}</td>
                                    <td class="p-2 text-slate-500 text-[11px] max-w-[150px] truncate" title="${h.observacoes || ''}">${h.observacoes || '-'}</td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>`;
        }

        Swal.fire({
            title: `<span class="text-slate-700">Histórico:</span> <span class="text-indigo-900">${alunoNome}</span>`,
            html: conteudoHtml,
            width: '600px',
            confirmButtonText: 'Fechar',
            confirmButtonColor: '#64748b'
        });

    } catch (e) {
        console.error("Erro ao carregar histórico", e);
        Swal.fire('Erro', 'Não foi possível carregar o histórico.', 'error');
    }
}

async function cancelarAulaGrupo(dados) {
    const confirmacao = await Swal.fire({
        title: 'Cancelar aula?',
        text: `Isso removerá a aula de ${dados.nome_exibicao}.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#ef4444',
        confirmButtonText: 'Sim, cancelar',
        cancelButtonText: 'Voltar'
    });

    if (confirmacao.isConfirmed) {
        try {
            // 1. Tratamento rigoroso da data para o formato que o Python (fromisoformat) aceita
            // Removemos os milissegundos e o 'Z' se houver
            let dataIso = typeof dados.data_inicio === 'string' 
                ? dados.data_inicio 
                : dados.data_inicio.toISOString();
            
            dataIso = dataIso.split('.')[0]; // Pega apenas YYYY-MM-DDTHH:MM:SS

            const params = new URLSearchParams();
            params.append('data_inicio', dataIso);

            // 2. Identificação precisa do ID (Turma ou Aluno)
            if (dados.is_turma || dados.turma_id) {
                const idTurma = dados.turma_id || (dados.alunos && dados.alunos[0].turma_id);
                if (idTurma) params.append('turma_id', Number(idTurma)); // Garante que é número
            } else {
                // Para aluno VIP/Individual
                const idAluno = dados.aluno_id || (dados.alunos && dados.alunos[0].aluno_id);
                if (idAluno) params.append('aluno_id', Number(idAluno)); // Garante que é número
            }

            // 3. Chamada ao servidor
            const urlCompleta = `${API_URL}/aulas/cancelar-grupo?${params.toString()}`;
            console.log("Chamando DELETE:", urlCompleta);

            const res = await fetchProtegido(urlCompleta, { method: 'DELETE' });
            const respostaServidor = await res.json();

            if (res.ok) {
                Toast.fire({ icon: 'success', title: 'Aula cancelada!' });
                carregarAgenda();
            } else {
                // 4. Tratamento amigável para o erro 422 do FastAPI
                let msgErro = "Erro desconhecido";
                
                if (Array.isArray(respostaServidor.detail)) {
                    // O FastAPI manda uma lista de erros no 422
                    msgErro = respostaServidor.detail.map(e => `${e.loc[1]}: ${e.msg}`).join("<br>");
                } else if (typeof respostaServidor.detail === 'string') {
                    msgErro = respostaServidor.detail;
                }

                Swal.fire({
                    title: 'Erro no Servidor',
                    html: `<div class="text-left text-sm text-red-600 font-mono">${msgErro}</div>`,
                    icon: 'error'
                });
            }
        } catch (e) {
            console.error("Erro técnico:", e);
            Swal.fire('Erro', 'Não foi possível conectar ao servidor.', 'error');
        }
    }
}

async function carregarEstatisticas() {
    try {
        const res = await fetchProtegido(`${API_URL}/aulas/admin/estatisticas-mes`);
        const d = await res.json();

        const statTaxa = document.getElementById('statTaxa');
        const statTotal = document.getElementById('statTotal');
        const statFaltosos = document.getElementById('statFaltosos');

        // 1. Atualiza os valores de texto
        statTaxa.innerText = `${d.taxa_presenca}%`;
        statTotal.innerText = d.total_aulas;

        // 2. Lógica de Cores Dinâmicas para a Taxa de Frequência
        // Removemos as cores antigas antes de aplicar a nova
        statTaxa.classList.remove('text-indigo-900', 'text-red-600', 'text-yellow-600', 'text-green-600');
        
        if (d.taxa_presenca < 50) {
            statTaxa.classList.add('text-red-600');    // Crítico (Vermelho)
        } else if (d.taxa_presenca < 85) {
            statTaxa.classList.add('text-yellow-600'); // Atenção (Amarelo)
        } else {
            statTaxa.classList.add('text-green-600');  // Ótimo (Verde)
        }

        // 3. Atualiza a lista de alunos faltosos
        const listaFaltosos = d.alunos_faltosos
            .map(a => `${a.nome} (${a.faltas})`)
            .join(', ');
        
        statFaltosos.innerText = d.alunos_faltosos.length > 0 
            ? `Crítico: ${listaFaltosos}` 
            : "Todos os alunos em dia!";
            
    } catch (e) {
        console.error("Erro ao carregar stats", e);
    }
}

async function carregarHistoricoGeral() {
    const container = document.getElementById('listaHistoricoGeral');
    if (!container) return;
    
    container.innerHTML = '<tr><td colspan="4" class="text-center py-10 text-slate-400">Carregando...</td></tr>';
    
    try {
        carregarEstatisticas();

        const res = await fetchProtegido(`${API_URL}/aulas/admin/historico-geral`);
        const sessoes = await res.json();
        
        container.innerHTML = "";
        if (!sessoes || sessoes.length === 0) {
            container.innerHTML = '<tr><td colspan="4" class="text-center py-10 text-slate-400">Nenhum registro encontrado.</td></tr>';
            return;
        }

        sessoes.forEach((sessao, index) => {
            const dataFmt = new Date(sessao.data).toLocaleDateString('pt-BR');
            const totalAlunos = sessao.alunos.length;
            
            // Transformamos a lista de alunos em texto seguro para passar pro botão
            const alunosJSON = JSON.stringify(sessao.alunos).replace(/"/g, '&quot;');

            container.innerHTML += `
                <tr class="border-b hover:bg-slate-50 transition">
                    <td class="p-4 font-bold text-slate-700">${dataFmt}</td>
                    <td class="p-4">
                        <div class="flex flex-col">
                            <span class="font-black text-indigo-900 uppercase italic tracking-tighter">${sessao.nome_exibicao}</span>
                            <span class="text-[9px] text-slate-400 font-bold uppercase">${sessao.is_turma ? 'Grupo / Duo' : 'Individual'}</span>
                        </div>
                    </td>
                    <td class="p-4 text-center">
                        <span class="px-2 py-1 rounded-md bg-slate-100 text-slate-500 font-black text-[10px]">
                            ${totalAlunos} ALUNO(S)
                        </span>
                    </td>
                    <td class="p-4 text-center">
                        <button onclick="abrirChamadaRetroativaGrupo('${sessao.nome_exibicao}', '${alunosJSON}')" 
                            class="bg-indigo-600 text-white px-3 py-2 rounded-xl text-[10px] font-black uppercase hover:bg-indigo-700 transition flex items-center gap-2 mx-auto shadow-lg shadow-indigo-100">
                            <i class="fa-solid fa-clipboard-user"></i> Ver Chamada
                        </button>
                    </td>
                </tr>
            `;
        });
    } catch (e) {
        console.error(e);
        container.innerHTML = '<tr><td colspan="4" class="text-center py-10 text-red-400">Erro ao processar histórico.</td></tr>';
    }
}


function filtrarHistorico() {
    const input = document.getElementById("buscaHistorico");
    const filtro = input.value.toLowerCase();
    const tabela = document.getElementById("listaHistoricoGeral");
    const linhas = tabela.getElementsByTagName("tr");

    for (let i = 0; i < linhas.length; i++) {
        // Pega o texto da coluna Data (0) e Aluno (1)
        const colunaData = linhas[i].getElementsByTagName("td")[0];
        const colunaAluno = linhas[i].getElementsByTagName("td")[1];
        
        if (colunaData || colunaAluno) {
            const textoData = colunaData.textContent || colunaData.innerText;
            const textoAluno = colunaAluno.textContent || colunaAluno.innerText;
            
            // Se o que o usuário digitou estiver na data ou no nome do aluno, mostra a linha
            if (textoData.toLowerCase().indexOf(filtro) > -1 || textoAluno.toLowerCase().indexOf(filtro) > -1) {
                linhas[i].style.display = "";
            } else {
                linhas[i].style.display = "none";
            }
        }
    }
}


async function verRelatorio(alunoId, nomeAluno) {
    Swal.fire({ title: 'Carregando relatório...', didOpen: () => { Swal.showLoading(); } });

    try {
        const res = await fetchProtegido(`${API_URL}/aulas/relatorio-aluno/${alunoId}`);
        const dados = await res.json();

        if (dados.length === 0) {
            Swal.fire('Vazio', 'Este aluno ainda não possui aulas registradas no histórico.', 'info');
            return;
        }

        // Monta a tabela em HTML
        let tabelaHtml = `
            <div class="max-h-96 overflow-y-auto">
                <table class="w-full text-left text-xs border-collapse">
                    <thead>
                        <tr class="border-b bg-slate-50">
                            <th class="p-2">Data</th>
                            <th class="p-2">Presença</th>
                            <th class="p-2">Avaliação/Desempenho</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${dados.map(h => `
                            <tr class="border-b hover:bg-slate-50">
                                <td class="p-2 font-bold">${h.data}</td>
                                <td class="p-2 text-center">${h.presenca}</td>
                                <td class="p-2">
                                    <div class="font-medium text-blue-600">${h.desempenho}</div>
                                    <div class="text-[10px] text-slate-400 italic">${h.observacao}</div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        Swal.fire({
            title: `Relatório: ${nomeAluno}`,
            html: tabelaHtml,
            width: '600px',
            confirmButtonText: 'Fechar'
        });

    } catch (e) {
        Swal.fire('Erro', 'Não foi possível carregar o relatório.', 'error');
    }
}