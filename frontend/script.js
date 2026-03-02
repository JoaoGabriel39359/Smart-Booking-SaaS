const API_URL = 'http://127.0.0.1:8000';
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
}

// --- GESTÃO DE ALUNOS (COM NOVOS CAMPOS E CORREÇÃO 422) ---
async function carregarAlunos() {
    const container = document.getElementById('listaAlunos');
    try {
        const res = await fetch(`${API_URL}/alunos/`);
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
                <div class="flex gap-3">
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
        const response = await fetch(`/turmas/${turmaId}/adicionar-aluno?aluno_id=${alunoId}`, {
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
            const res = await fetch(`${API_URL}/alunos/`, {
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
            await fetch(`${API_URL}/alunos/${id}`, { method: 'DELETE' });
            carregarAlunos();
            Toast.fire({icon: 'success', title: 'Excluído!'});
        }
    });
}

// --- GESTÃO DE TURMAS ---
async function carregarTurmas() {
    const container = document.getElementById('listaTurmas');
    try {
        const res = await fetch(`${API_URL}/turmas/`);
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
    // 1. Busca os alunos sem turma
    const respAlunos = await fetch(`${API_URL}/alunos/sem-turma`);
    const alunosLivres = await respAlunos.json();

    // 2. Cria o HTML da lista de alunos
    let listaAlunosHTML = alunosLivres.map(al => `
        <label class="flex items-center gap-2 p-2 hover:bg-slate-50 rounded-lg cursor-pointer border border-slate-100">
            <input type="checkbox" name="aluno-turma" value="${al.id}" class="rounded text-indigo-600">
            <span class="text-sm text-slate-700">${al.nome} ${al.sobrenome || ''}</span>
        </label>
    `).join('');

    if (alunosLivres.length === 0) {
        listaAlunosHTML = '<p class="text-xs text-red-400">Nenhum aluno disponível sem turma.</p>';
    }

    // 3. Abre o modal
    const { value: formValues } = await Swal.fire({
        title: 'Criar Nova Turma',
        html: `
            <div class="text-left space-y-4">
                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Nome do Grupo</label>
                    <input id="t-nome" class="swal2-input-custom" placeholder="Ex: Duo de Quinta">
                </div>
                
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="text-[10px] font-bold uppercase text-slate-400">Dia</label>
                        <select id="t-dia" class="swal2-input-custom">
                            <option value="Segunda">Segunda</option>
                            <option value="Terça">Terça</option>
                            <option value="Quarta">Quarta</option>
                            <option value="Quinta">Quinta</option>
                            <option value="Sexta">Sexta</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-[10px] font-bold uppercase text-slate-400">Horário</label>
                        <input id="t-hora" type="time" class="swal2-input-custom">
                    </div>
                </div>

                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Modalidade</label>
                    <select id="t-tipo" class="swal2-input-custom">
                        <option value="TEAM">TEAM (até 6)</option>
                        <option value="DUO">DUO (2 alunos)</option>
                        <option value="VIP">VIP (1 aluno)</option>
                    </select>
                </div>

                <div>
                    <label class="text-[10px] font-bold uppercase text-slate-400">Selecionar Alunos</label>
                    <div class="max-h-40 overflow-y-auto mt-2 space-y-1">
                        ${listaAlunosHTML}
                    </div>
                </div>
            </div>
        `,
        preConfirm: () => {
            const nome = document.getElementById('t-nome').value;
            const dia = document.getElementById('t-dia').value;
            const hora = document.getElementById('t-hora').value;
            const tipo = document.getElementById('t-tipo').value;
            const selecionados = Array.from(document.querySelectorAll('input[name="aluno-turma"]:checked')).map(el => Number(el.value));

            if (!nome || !hora || selecionados.length === 0) {
                return Swal.showValidationMessage('Preencha o nome, horário e selecione ao menos um aluno.');
            }

            return { 
                nome_turma: nome, // <--- Aqui deve bater com o Python
                tipo: tipo, 
                dia_semana: dia, 
                horario: hora, 
                aluno_ids: selecionados 
            };
        }
    });

    if (formValues) {
        const res = await fetch(`${API_URL}/turmas/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(formValues)
        });
        if (res.ok) {
            Toast.fire({icon: 'success', title: 'Turma criada!'});
            carregarTurmas();
        } else {
            const err = await res.json();
            Swal.fire("Erro", err.detail || "Erro ao criar", "error");
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
        const res = await fetch(`${API_URL}/turmas/${id}`, { method: 'DELETE' });
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
        const res = await fetch(`${API_URL}/aulas/lista-professor`);
        const aulas = await res.json();
        
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
                if(btn) btn.onclick = () => abrirChamada(a); 
            }, 0);
        });
    } catch (e) { console.error("Erro na agenda", e); }
}

// FUNÇÃO QUE ABRE O POPUP DE CHAMADA E NOTA
async function abrirChamada(dadosAgrupados) {
    // 1. Geramos a lista de presença para cada aluno da turma/VIP
    const listaAlunosHtml = dadosAgrupados.alunos.map(al => `
        <div class="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100 mb-2">
            <span class="font-bold text-slate-700 text-sm">${al.nome}</span>
            <select id="status-${al.aula_id}" class="border-2 border-slate-200 rounded-lg p-1 text-xs font-bold outline-none focus:border-indigo-500">
                <option value="presente">✅ Presente</option>
                <option value="ausente">❌ Ausente</option>
            </select>
        </div>
    `).join('');

    const { value: formValues } = await Swal.fire({
        title: `<span class="text-slate-700">Chamada:</span> <span class="text-indigo-900">${dadosAgrupados.nome_exibicao}</span>`,
        html: `
            <div class="text-left space-y-4 p-2">
                <label class="block text-[10px] font-bold uppercase text-slate-400 tracking-wider">Lista de Presença</label>
                <div class="max-h-40 overflow-y-auto pr-1">
                    ${listaAlunosHtml}
                </div>

                <label class="block text-[10px] font-bold uppercase text-slate-400 tracking-wider mt-4">Desempenho da Turma</label>
                <div class="grid grid-cols-3 gap-3">
                    <label class="cursor-pointer">
                        <input type="radio" name="nota" value="Ruim" class="peer hidden">
                        <div class="text-center p-3 border-2 border-slate-100 rounded-xl transition-all peer-checked:bg-red-50 peer-checked:border-red-500 peer-checked:scale-95">
                            <div class="text-xl mb-1">🙁</div>
                            <div class="text-[10px] font-bold text-slate-600 uppercase">Ruim</div>
                        </div>
                    </label>

                    <label class="cursor-pointer">
                        <input type="radio" name="nota" value="Médio" class="peer hidden">
                        <div class="text-center p-3 border-2 border-slate-100 rounded-xl transition-all peer-checked:bg-yellow-50 peer-checked:border-yellow-500 peer-checked:scale-95">
                            <div class="text-xl mb-1">😐</div>
                            <div class="text-[10px] font-bold text-slate-600 uppercase">Médio</div>
                        </div>
                    </label>

                    <label class="cursor-pointer">
                        <input type="radio" name="nota" value="Bom" class="peer hidden" checked>
                        <div class="text-center p-3 border-2 border-slate-100 rounded-xl transition-all peer-checked:bg-green-50 peer-checked:border-green-500 peer-checked:scale-95">
                            <div class="text-xl mb-1">🤩</div>
                            <div class="text-[10px] font-bold text-slate-600 uppercase">Bom</div>
                        </div>
                    </label>
                </div>

                <label class="block text-[10px] font-bold uppercase text-slate-400 tracking-wider mt-4">Conteúdo Estudado (Geral)</label>
                <textarea id="ch-obs" class="w-full border-2 border-slate-100 rounded-xl p-3 text-sm h-24 focus:border-indigo-500 outline-none transition-all" placeholder="O que foi trabalhado hoje?"></textarea>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Confirmar Chamada',
        cancelButtonText: 'Voltar',
        confirmButtonColor: '#2563eb',
        cancelButtonColor: '#94a3b8',
        preConfirm: () => {
            // Mapeamos a presença de cada aluno individualmente
            return dadosAgrupados.alunos.map(al => ({
                aula_id: al.aula_id,
                status: document.getElementById(`status-${al.aula_id}`).value,
                desempenho: document.querySelector('input[name="nota"]:checked').value,
                observacoes: document.getElementById('ch-obs').value
            }));
        }
    });

    if (formValues) {
        try {
            // Como agora temos uma lista de presenças (mesmo que seja só 1 aluno VIP), fazemos um loop
            let falhas = 0;
            
            for (const chamada of formValues) {
                const url = `${API_URL}/aulas/${chamada.aula_id}/presenca?status=${chamada.status}&desempenho=${chamada.desempenho}&observacoes=${encodeURIComponent(chamada.observacoes)}`;
                const res = await fetch(url, { method: 'PATCH' });
                if (!res.ok) falhas++;
            }
            
            if (falhas === 0) {
                Toast.fire({ icon: 'success', title: 'Chamada realizada com sucesso!' });
                carregarAgenda();
            } else {
                Swal.fire('Atenção', `Chamada concluída, mas ${falhas} registros falharam.`, 'warning');
            }
        } catch (e) {
            console.error(e);
            Swal.fire('Erro', 'Falha na comunicação com o servidor', 'error');
        }
    }
}

async function cancelarAula(id) {
    if(confirm("Deseja cancelar esta aula?")) {
        await fetch(`${API_URL}/aulas/${id}`, { method: 'DELETE' });
        carregarAgenda();
    }
}

// --- GRADE BASE E CALENDÁRIO ---
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
        grid.innerHTML += `
            <div onclick="selecionarDia(this, ${dia}, ${new Date(ano,mes,dia).getDay()})" 
                 class="bg-white h-24 p-2 border border-slate-100 hover:border-indigo-500 cursor-pointer transition-colors relative">
                <span class="text-xs font-black ${ehHoje ? 'bg-indigo-600 text-white w-6 h-6 flex items-center justify-center rounded-full' : 'text-slate-300'}">
                    ${dia}
                </span>
            </div>`;
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
        const res = await fetch(`${API_URL}/aulas/grade`);
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
    await fetch(`${API_URL}/aulas/grade/${id}`, { method: 'DELETE' });
    carregarGridSemanal();
}

document.getElementById('formGrade').onsubmit = async (e) => {
    e.preventDefault();
    const dia = document.getElementById('diaSemanaOculto').value;
    const inicio = document.getElementById('inicioGrade').value;
    const fim = document.getElementById('fimGrade').value;
    if(dia === "") return Toast.fire({icon:'warning', title:'Selecione um dia no calendário'});
    
    await fetch(`${API_URL}/aulas/configurar-grade?dia=${dia}&inicio=${inicio}&fim=${fim}`, {method: 'POST'});
    Toast.fire({icon: 'success', title: 'Horário salvo!'});
    carregarTudoGrade();
};

function mudarMes(d) {
    dataAtualCalendario.setMonth(dataAtualCalendario.getMonth() + d);
    gerarCalendario();
}

// Inicialização
window.onload = () => {
    carregarAgenda();
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
        const res = await fetch(`${API_URL}/alunos/${aluno.id}`, {
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
    const response = await fetch('/alunos/sem-turma');
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
    // Feedback visual de carregamento
    Toast.fire({ icon: 'info', title: 'Gerando agenda...', timer: 1500 });

    try {
        const res = await fetch(`${API_URL}/turmas/gerar-mensal`, {
            method: 'POST'
        });
        const dados = await res.json();

        if (res.ok) {
            Swal.fire('Sucesso!', dados.msg, 'success');
            // Se você tiver uma função para carregar a agenda/calendário, chame-a aqui
            if (typeof carregarAgenda === "function") carregarAgenda();
        } else {
            Swal.fire('Erro', dados.detail || 'Erro ao gerar aulas', 'error');
        }
    } catch (e) {
        console.error(e);
        Swal.fire('Erro', 'Não foi possível conectar ao servidor.', 'error');
    }
}

async function gerarAulasDoMes() {
    const confirmacao = await Swal.fire({
        title: 'Gerar agenda do mês?',
        text: "O sistema criará automaticamente todas as aulas deste mês baseadas nos horários fixos das turmas.",
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#10b981', // Cor emerald
        confirmButtonText: 'Sim, gerar agora!',
        cancelButtonText: 'Cancelar'
    });

    if (confirmacao.isConfirmed) {
        // Mostra um carregando enquanto o Python trabalha
        Swal.fire({ title: 'Gerando...', allowOutsideClick: false, didOpen: () => { Swal.showLoading(); } });

        try {
            const res = await fetch(`${API_URL}/turmas/gerar-mensal`, { method: 'POST' });
            const dados = await res.json();

            if (res.ok) {
                Swal.fire('Sucesso!', dados.msg, 'success');
                // Recarrega a agenda automaticamente para as aulas aparecerem
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
    const res = await fetch(`${API_URL}/alunos/`);
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
        const res = await fetch(`${API_URL}/aulas/avulsa`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        if (res.ok) {
            Toast.fire({ icon: 'success', title: 'Aula agendada!' });
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

    const res = await fetch(`/alunos/${id}`, {
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
        const res = await fetch(`${API_URL}/alunos/`);
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
        const res = await fetch(`${API_URL}/turmas/${turmaId}/adicionar-aluno/${alunoId}`, {
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
        const res = await fetch(`${API_URL}/aulas/historico/${alunoId}`);
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
        text: `Isso removerá a aula de todos os alunos da ${dados.nome_exibicao}.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#ef4444',
        confirmButtonText: 'Sim, cancelar tudo',
        cancelButtonText: 'Voltar'
    });

    if (confirmacao.isConfirmed) {
        try {
            // Se for turma, pegamos o ID da turma. Se for VIP, pegamos o ID do aluno.
            const params = new URLSearchParams({
                data_inicio: dados.data_inicio
            });

            if (dados.is_turma) {
                // Aqui você deve garantir que o seu backend enviou o campo 'turma_id'
                params.append('turma_id', dados.alunos[0].turma_id || dados.turma_id); 
            } else {
                params.append('aluno_id', dados.alunos[0].aluno_id);
            }

            const res = await fetch(`${API_URL}/aulas/cancelar-grupo?${params.toString()}`, { 
                method: 'DELETE' 
            });

            if (res.ok) {
                Toast.fire({ icon: 'success', title: 'Aula(s) cancelada(s)!' });
                carregarAgenda();
            } else {
                const erro = await res.json();
                Swal.fire('Erro', erro.detail || 'Erro ao cancelar', 'error');
            }
        } catch (e) {
            console.error(e);
            Swal.fire('Erro', 'Não foi possível conectar ao servidor.', 'error');
        }
    }
}