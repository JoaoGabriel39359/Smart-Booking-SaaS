# Plano de Melhorias — agenda_saas

Documento de trabalho: diagnóstico técnico + prompts prontos para colar no Gemini.
Ordem de execução recomendada: P0 → P1 → P2 → P3 → P4 → P5 → P6.

---

## 0. Diagnóstico geral da arquitetura

**Stack:** FastAPI + SQLAlchemy + APScheduler + Evolution API (WhatsApp) + Google Calendar.
Frontend: HTML/Tailwind + `frontend/script.js` (1543 linhas, tudo global) + SweetAlert.

### Problema-raiz nº1: duas tabelas concorrentes para a mesma coisa
`Aula` (agenda) e `HistoricoAula` (chamada/pedagógico) guardam o mesmo evento **sem nenhuma
chave estrangeira entre elas**. Elas são casadas por `aluno_id + func.date(data)` em 6 lugares
diferentes (`aulas.py` linhas 271, 395, 442, 341). Consequências reais:

- Se o aluno tem **2 aulas no mesmo dia** (exatamente o caso do plano de 1h → 2h), marcar
  presença ou cancelar uma aula afeta a outra (ou as duas).
- `DELETE /aulas/{id}`, `DELETE /aulas/cancelar-grupo` e o cancelamento de turma **apagam a
  `Aula` mas não mexem no `HistoricoAula`**. A aba Histórico e o calendário do painel leem
  `/aulas/admin/historico-geral`, que só olha `HistoricoAula` → **é por isso que a aula
  excluída continua aparecendo como agendada** (reclamação nº5 do cliente).
- `gerar_agenda.py:80` grava `data_aula=inicio_dt.date()` (perde a hora), enquanto
  `aulas.py:116` grava `data_aula=inicio` (com hora). O casamento por data fica ainda mais frágil.

### Problema-raiz nº2: crédito de reposição tem duas fontes de verdade
`Aluno.creditos_reposicao` (contador inteiro) **e** a contagem de `Aula` com
`status=cancelado AND validade_reposicao >= now()` (`aulas.py:50`). Elas divergem, e
`DELETE /turmas/{id}` apaga as `Aula` canceladas → **o aluno perde os créditos** (reclamação nº2).
Pior: `marcar_aula` zera `pessoinha.creditos_reposicao = 0` quando a contagem dá zero.

### Problema-raiz nº3: Enum vs string
`StatusAula.presente` tem `name="presente"` e `value="Presente"`. O SQLAlchemy `Enum` grava o
**name**. O código compara às vezes por Enum (`== StatusAula.marcada`), às vezes por string
(`== "cancelado"`, `.in_(['presente','ausente','Presente','Ausente'])` — gambiarra em
`aulas.py:541`), e `turmas.py:80` insere a string crua `status="marcada"`.
Qualquer filtro escrito com `.value` retorna vazio silenciosamente.

### Problema-raiz nº4: sem migrations
Só existe `Base.metadata.create_all()`. Isso **cria tabelas novas, mas nunca adiciona coluna em
tabela existente**. Toda mudança de modelo abaixo exige `ALTER TABLE` manual no Postgres do
Render (ou instalar Alembic — recomendado, ver P0).

### Problema-raiz nº5: fuso horário
As aulas são gravadas em horário de Brasília (naive), mas `lembretes.py`, `scheduler.py`,
`lembrete_imediato.py` e `horarios_livres` usam `datetime.now()` — que no Render **é UTC**.
Os lembretes de 1h/20min disparam com 3h de erro (ou nunca). `aulas.py` e `portal.py` já usam
`pytz.timezone('America/Sao_Paulo')`; o resto não.

### Outros pontos (menores, mas resolva)
- `app/auth.py:9` — `SECRET_KEY` hardcoded no código-fonte. Mover para `.env` e **trocar a chave**.
- URL `https://smart-booking-saas.onrender.com` hardcoded em 3 arquivos → virar `BASE_URL` no `.env`.
- `webhook.py:26` — link do portal montado com `http://seu-ip-ou-dominio:8000/portal/{aluno.id}`:
  domínio placeholder **e** usa `id` em vez de `token_acesso`. O webhook está quebrado.
- `models.py:62 e 68` — coluna `validade_reposicao` declarada **duas vezes**.
- `aulas.py:467-469` — a mesma query executada duas vezes seguidas.
- `alunos.py:99` (`GET /alunos/portal/{aluno_id}`) é um **segundo portal duplicado**, com HTML
  inline e botão que só dá `alert()`. É código morto; o portal real é `portal.py` + `portal.html`.
- `app/services/scheduler.py` chama `scheduler.start()` **no import** e duplica os jobs do
  `main.py`. Hoje ninguém importa, mas é uma bomba armada. `app/jobs/` também está órfão.
- `historico-geral` faz N+1 queries (um `SELECT` de aluno por registro).
- Um único `google_event_id` é compartilhado por todos os alunos da turma; cancelar 1 aluno
  remove o evento do Google de todo mundo.
- `.gitignore` tem uma linha `database.py` no final que pode ignorar `app/database.py` por acidente.
- Frontend: `script.js` monolítico, sem módulos, HTML montado por `innerHTML` com dados do banco.

---

## Regras de ouro para passar ao Gemini (cole junto com QUALQUER prompt)

```
CONTEXTO DO PROJETO: FastAPI + SQLAlchemy (Postgres em produção, SQLite local),
frontend em HTML/Tailwind + JS puro (frontend/script.js, funções globais, SweetAlert2 e
fetchProtegido() para chamadas autenticadas com Bearer token).

REGRAS OBRIGATÓRIAS:
1. NÃO existe Alembic. Se você criar/alterar coluna, entregue TAMBÉM o comando
   ALTER TABLE em SQL puro compatível com Postgres para eu rodar à mão.
2. Status de aula: SEMPRE use o Enum StatusAula (StatusAula.marcada etc.), NUNCA string
   crua e NUNCA .value em filtros — o SQLAlchemy persiste o NAME do Enum.
3. Datas: use SEMPRE o helper agora_br() (pytz America/Sao_Paulo, .replace(tzinfo=None)).
   Nunca datetime.now() puro.
4. Não reescreva arquivos inteiros: me entregue apenas os blocos alterados, com o nome do
   arquivo e a função onde entra.
5. Não quebre nenhuma rota existente e não altere o schema de resposta que o script.js já consome.
6. Toda rota de admin leva `usuario: str = Depends(verificar_token)`; rotas do aluno
   autenticam pelo `Aluno.token_acesso` na URL.
7. Responda em português, sem explicação longa: código + o que colar onde.
```

---

## P0 — Higiene e base (fácil, faça primeiro)

**Prompt para o Gemini:**
```
[cole as REGRAS DE OURO acima]

Arquivos anexados: app/auth.py, app/models.py, app/main.py, app/database.py,
app/routes/portal.py, app/routes/webhook.py, app/services/lembretes.py, app/routes/alunos.py

Faça estas correções pontuais:

1. Crie app/core/config.py com: SECRET_KEY, BASE_URL, TELEFONE_PROFESSOR e TIMEZONE lidos de
   os.getenv com defaults seguros, e uma função agora_br() que retorna
   datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None).
   Liste as variáveis que eu preciso adicionar no .env.
2. app/auth.py: pare de usar a SECRET_KEY hardcoded, importe de core/config.
3. Substitua TODAS as ocorrências hardcoded de "https://smart-booking-saas.onrender.com"
   por BASE_URL. Diga em quais arquivos/linhas.
4. Substitua datetime.now() por agora_br() em app/services/lembretes.py,
   app/services/scheduler.py, app/jobs/lembrete_imediato.py e na rota
   /aulas/horarios-livres. Explique numa linha por que isso conserta os lembretes no Render.
5. app/models.py: remova a coluna duplicada validade_reposicao da classe Aula (declarada 2x).
6. app/routes/aulas.py, rota /admin/historico-geral: remova a query duplicada
   (a linha `registros = query.order_by(...)` aparece 2x) e elimine o N+1 fazendo
   um único join com Aluno em vez de um SELECT por registro.
7. app/routes/webhook.py: o link do portal está usando um domínio placeholder e o aluno.id.
   Corrija para f"{BASE_URL}/portal/{aluno.token_acesso}".
8. DELETE a rota GET /alunos/portal/{aluno_id} de app/routes/alunos.py (portal duplicado e
   morto — o portal real é o /portal/{token} em portal.py).
9. app/services/scheduler.py: remova o scheduler.start() de nível de módulo (duplica os jobs
   do main.py). Se o arquivo ficar redundante, diga que pode ser apagado.
```

---

## P1 — Demanda 1: acesso e envio do link do portal (fácil)

O `token_acesso` **já existe** e já vem no JSON de `GET /alunos/` — só não está exposto na tela.
Falta: botão de copiar/abrir, botão de enviar por WhatsApp na hora (hoje ele só recebe o link
no lembrete automático de 24h), e um backfill para alunos antigos com `token_acesso` nulo.

**Prompt para o Gemini:**
```
[cole as REGRAS DE OURO]

Arquivos anexados: app/routes/alunos.py, app/services/whatsapp.py, frontend/script.js
(função carregarAlunos, ~linha 60), app/core/config.py

Objetivo: o professor precisa acessar e reenviar o link do portal de cada aluno pelo painel,
sem esperar o lembrete automático de 24h.

BACKEND (app/routes/alunos.py):
1. GET /alunos/{aluno_id}/link-portal -> retorna {"link": f"{BASE_URL}/portal/{token}"}.
   Se aluno.token_acesso for None (alunos antigos), gere um uuid4 novo, salve e retorne.
2. POST /alunos/{aluno_id}/enviar-portal -> usa BackgroundTasks + enviar_whatsapp para mandar
   ao telefone do aluno uma mensagem com saudação pelo nome e o link do portal.
   Retorna {"status":"enviado"}. Mesma lógica de gerar token se estiver nulo.
3. POST /alunos/regerar-tokens -> percorre todos os alunos com token_acesso nulo, gera uuid4,
   commita e retorna quantos foram corrigidos.
Todas com Depends(verificar_token).

FRONTEND (frontend/script.js):
4. No card de cada aluno em carregarAlunos(), adicione 3 botões pequenos (ícones SVG no
   mesmo estilo dos existentes):
   - "Abrir portal": window.open(link, '_blank')
   - "Copiar link": navigator.clipboard.writeText(link) + Swal toast de sucesso
   - "Enviar no WhatsApp": Swal.fire de confirmação, depois
     fetchProtegido(`${API_URL}/alunos/${id}/enviar-portal`, {method:'POST'})
   Use o campo token_acesso que JÁ vem no JSON de GET /alunos/ para montar o link
   (`${window.location.origin}/portal/${aluno.token_acesso}`), sem chamada extra.
```

---

## P2 — Demanda 5: aula excluída continua aparecendo (fácil-médio, ALTA PRIORIDADE)

**Prompt para o Gemini:**
```
[cole as REGRAS DE OURO]

Arquivos anexados: app/routes/aulas.py, app/routes/turmas.py, app/models.py,
app/services/gerar_agenda.py

BUG RELATADO: "cancelo/excluo aulas e turmas, mas elas continuam aparecendo na agenda
como agendadas".

CAUSA-RAIZ que você deve corrigir: as tabelas `aulas` (modelo Aula) e `historico_aulas`
(modelo HistoricoAula) representam o MESMO evento mas não têm FK entre si; são casadas por
aluno_id + func.date(). As rotas de exclusão apagam a Aula e deixam o HistoricoAula órfão, e
a aba Histórico/calendário do painel lê apenas /aulas/admin/historico-geral (só HistoricoAula)
— então o evento excluído continua aparecendo.

FAÇA:
1. Adicione em HistoricoAula a coluna `aula_id = Column(Integer, ForeignKey("aulas.id",
   ondelete="CASCADE"), nullable=True, index=True)` + relationship. Me dê o ALTER TABLE.
2. Preencha `aula_id` em TODOS os pontos que criam HistoricoAula: /aulas/marcar,
   /aulas/avulsa, gerar_agenda.py (use db.flush() para ter o Aula.id antes).
3. Padronize gerar_agenda.py: `data_aula=inicio_dt` (datetime completo), não `.date()`.
4. Crie um helper único em app/routes/aulas.py:
   `def remover_aula_completa(db, aula, motivo: str, apagar_google: bool = True)`
   que: remove o evento do Google (só se nenhuma outra Aula viva compartilhar o mesmo
   google_event_id — hoje a turma inteira compartilha 1 evento e cancelar 1 aluno apaga o
   evento de todos), apaga/atualiza os HistoricoAula ligados (por aula_id, com fallback para
   aluno_id+data para os registros antigos sem FK) e por fim apaga a Aula.
5. Reescreva DELETE /aulas/{aula_id} e DELETE /aulas/cancelar-grupo para usarem esse helper.
6. Em DELETE /turmas/{turma_id}: (a) apague também as Aula dos alunos da turma que estejam
   com turma_id NULL mas no mesmo dia/hora dos HorarioAula da turma (aulas avulsas e
   reposições ficam órfãs hoje); (b) NÃO apague o HistoricoAula de aulas já realizadas —
   apague só os registros com chamada_realizada=False de aulas FUTURAS, para preservar o
   histórico pedagógico; (c) NÃO apague as Aula com status=cancelado que tenham
   validade_reposicao no futuro, porque elas são a base de cálculo dos créditos do aluno.
7. Varredura de consistência de Enum: em TODO o app/routes/aulas.py troque comparações de
   status por string ("marcada", "cancelado", ['presente','ausente','Presente','Ausente'])
   pelo Enum StatusAula. Idem `status="marcada"` em turmas.py:80.
8. Crie uma rota de saneamento POST /aulas/admin/sanear-orfaos que apague HistoricoAula sem
   Aula correspondente (para limpar o lixo que já está no banco de produção) e retorne a
   contagem. Preciso rodar isso uma vez após o deploy.
```

---

## P3 — Demanda 3: aba de Frequência, Cancelamentos e Créditos (fácil)

Os dados já existem, faltam os endpoints e a tela.

**Prompt para o Gemini:**
```
[cole as REGRAS DE OURO]

Arquivos anexados: app/models.py, app/routes/aulas.py, frontend/index.html,
frontend/script.js (veja trocarAba() na linha 12 e carregarEstatisticas() na 1257 como padrão)

Objetivo: nova aba "Frequência" no painel, com 3 blocos.

BACKEND — crie app/routes/relatorios.py (prefix="/relatorios", registre em main.py):
1. GET /relatorios/frequencia?dias=30 -> por aluno: nome, total de aulas no período,
   presenças, faltas, cancelamentos, taxa_presenca (%), data da última aula.
   Baseie em HistoricoAula (chamada_realizada=True) + Aluno, com um único join/group_by
   (sem loop de queries).
2. GET /relatorios/cancelamentos-semana -> aulas com status=StatusAula.cancelado nos
   últimos 7 dias: nome do aluno, telefone, data/hora da aula cancelada, se gerou crédito
   (validade_reposicao não nula), validade formatada dd/mm/aaaa.
3. GET /relatorios/creditos -> alunos com crédito a usar: nome, telefone, qtd de créditos
   VÁLIDOS (contagem de Aula com status=cancelado e validade_reposicao >= agora_br()),
   a data de validade mais próxima, e quantos já venceram.
   IMPORTANTE: use essa contagem como fonte única de verdade e ATUALIZE o campo
   Aluno.creditos_reposicao com ela na mesma chamada, para os dois pararem de divergir.

FRONTEND:
4. Em index.html, adicione o botão de aba "Frequência" (id="btnTabFrequencia") ao lado de
   "Grade Base" e a <section id="abaFrequencia" class="aba-content hidden">, seguindo
   exatamente o padrão visual/Tailwind das seções existentes: 3 cards, sendo o primeiro
   uma tabela de frequência com filtro de busca, e os outros dois listas.
5. Em script.js: registre 'frequencia' em trocarAba(), crie carregarFrequencia() que
   chama os 3 endpoints em Promise.all e renderiza. Em cada aluno da lista de créditos,
   um botão "Cobrar reposição" que dispara a mensagem de WhatsApp com o link do portal
   (reutilize POST /alunos/{id}/enviar-portal criado na etapa P1).
```

---

## P4 — Demanda 2 (parte fácil): editar aluno de verdade (fácil-médio)

Hoje `AlunoEdit` não permite mudar `limite_aulas_semana`, `turma_id` nem créditos — é
justamente o que muda quando o aluno troca de plano.

**Prompt para o Gemini:**
```
[cole as REGRAS DE OURO]

Arquivos anexados: app/routes/schemas.py, app/routes/alunos.py, frontend/script.js
(abrirModalEditarAluno ~linha 867 e salvarEdicaoAluno ~linha 1046)

PROBLEMA: o professor não consegue editar informações do aluno quando ele troca de plano
(ex: de 1h para 2h por semana). Hoje ele apaga e recria a turma, e o aluno perde os créditos.

FAÇA:
1. Em schemas.py, adicione ao AlunoEdit (todos Optional): limite_aulas_semana: Optional[int],
   turma_id: Optional[int], creditos_reposicao: Optional[int].
2. Em PUT /alunos/{aluno_id}: aplique esses campos. Atenção: use um padrão
   `if dados.campo is not None` em vez de `or` — o código atual usa
   `aluno.nome = dados.nome or aluno.nome`, o que impossibilita limpar um campo e trata 0
   como ausente (bug real para limite_aulas_semana e creditos_reposicao).
   Refatore para iterar sobre dados.model_dump(exclude_unset=True).
3. Se turma_id mudar, valide a capacidade da turma destino (VIP:1, DUO:2, TEAM:6) e retorne
   400 com mensagem clara se estourar. NÃO apague nem recrie nada de créditos.
4. No modal abrirModalEditarAluno do script.js, adicione os campos: select de turma
   (carregue GET /turmas/), input numérico "Aulas por semana" e input numérico
   "Créditos de reposição", já preenchidos com os valores atuais. Atualize
   salvarEdicaoAluno para enviá-los.
```

---

## P5 — Demanda 2 (parte difícil): editar TURMA sem destruir a agenda ✅ FEITO

Implementado em 31/08/2026. O que mudou:

- **`PUT /turmas/{turma_id}`** ([turmas.py](app/routes/turmas.py)) agora aceita `nome_turma`,
  `meet_link`, `tipo`, `duracao_minutos`, `horarios[{dia,hora}]` e `aluno_ids[]`.
  Valida capacidade por tipo **antes** de alterar qualquer coisa, reescreve os `HorarioAula`,
  religa/desliga alunos e regera 4 semanas via `gerar_aulas_da_semana`.
- **Créditos preservados:** a limpeza apaga só `Aula` **futuras** com `status=marcada`.
  Aulas `cancelado` com `validade_reposicao` (a base do crédito) e aulas já realizadas
  (histórico pedagógico) ficam intactas. Validado em teste de fumaça.
- **`duracao_minutos` passou a valer de verdade:** novo `app/services/agendamento.py` com
  `duracao_aula_minutos(db, aluno)`, usado em `/aulas/marcar`, `/aulas/avulsa` e
  `/reagendar/{token}`. Antes os três cravavam `timedelta(hours=1)` e o plano de 2h era fake.
- **Bug corrigido em `gerar_agenda.py`:** a trava de duplicidade olhava só
  `alunos_afetados[0]`; aluno recém-adicionado numa turma existente **nunca** recebia aula.
  Agora é por aluno, e reaproveita o `google_event_id` do horário em vez de duplicar evento.
- **`GET /turmas/`** passou a devolver `duracao_minutos` e `horarios[{dia,hora}]`.
- **Frontend:** `abrirModalEditarTurma` agora edita plano, duração, dias/horários
  (adicionar/remover) e composição de alunos, com aviso sobre a regeneração da agenda.

Sem `ALTER TABLE` necessário — nenhuma coluna nova.

---

## P6 — Demanda 4: professores + vários horários por hora

**Prompt para o Gemini** (as linhas citadas são do estado atual do repositório):
```
[cole as REGRAS DE OURO]

Arquivos anexados: app/models.py, app/routes/aulas.py, app/routes/portal.py,
app/routes/turmas.py, app/services/gerar_agenda.py, frontend/index.html,
frontend/script.js, frontend/templates/portal.html, app/main.py

OBJETIVO (pedido do cliente): cadastrar professores, liberar MAIS DE UM horário de reposição
na mesma hora (inclusive dois professores no mesmo horário), manter internamente de quem é
cada horário, e o aluno só descobrir o professor DEPOIS de agendar, via mensagem
"Reposição agendada com o professor X".

--- 1. MODELOS (app/models.py) ---
a) Nova classe Professor: id, nome (String, obrigatório), telefone (String, nullable),
   cor (String, nullable — para pintar o card na agenda), ativo (Boolean, default True).
b) GradeProfessor: adicione professor_id (FK professores.id, nullable=True, index=True) e
   capacidade (Integer, default=1, nullable=False) = quantas aulas simultâneas caben nesse turno.
c) Aula: adicione professor_id (FK professores.id, nullable=True, index=True) + relationship.
d) Turma: adicione professor_id (FK professores.id, nullable=True) + relationship.
Me entregue os ALTER TABLE / CREATE TABLE em SQL Postgres (não existe Alembic).

--- 2. CRUD (novo app/routes/professores.py, prefix="/professores", registrar no main.py) ---
GET / (lista, com contagem de turnos e de turmas de cada um), POST / , PUT /{id},
DELETE /{id} (só permita apagar se não houver Aula futura vinculada; senão retorne 400
sugerindo desativar via ativo=False). Use Pydantic, não `dados: dict`.

--- 3. GRADE COM VAGAS (app/routes/aulas.py) ---
e) POST /aulas/configurar-grade (linha 314): hoje recebe dia/inicio/fim por query param.
   Passe a aceitar também professor_id (opcional) e capacidade (default 1).
f) GET /aulas/grade (linha 321): retorne também professor_id, nome do professor e capacidade.
g) GET /aulas/horarios-livres (linha 195) — ESTA É A MUDANÇA PRINCIPAL.
   Hoje o código monta `horarios_possiveis` varrendo os turnos de hora em hora (linha 227) e
   depois faz `livres = [h for h in horarios_possiveis if h not in horarios_ocupados]`,
   o que BLOQUEIA A HORA INTEIRA globalmente assim que existe 1 aula qualquer nela.
   Reescreva para contagem de vagas POR TURNO da grade:
     - para cada GradeProfessor ativo do dia, gere os slots de hora em hora;
     - para cada slot, conte as Aula com status marcada/presente naquele horário
       COM O MESMO professor_id do turno (se o turno não tem professor, conte as aulas
       sem professor_id);
     - vagas = turno.capacidade - aulas_no_slot; se vagas > 0, o slot entra na resposta.
   Assim dois turnos (dois professores) na mesma hora geram duas vagas na mesma hora.
   RESPOSTA: mantenha a chave "horarios_livres", mas agora como lista de objetos
   [{"hora": "18:00", "grade_id": 3, "vagas": 1}] — sem NUNCA expor o nome do professor aqui.
   Agrupe por hora somando vagas, e devolva o grade_id de um turno com vaga.
h) POST /aulas/marcar (a checagem de conflito na linha 77 é global): passe a aceitar
   grade_id opcional; resolva o professor a partir do GradeProfessor; o conflito passa a ser
   por professor (Aula.professor_id == professor_id) e a respeitar a capacidade do turno.
   Grave Aula.professor_id. Se o aluno tem turma com professor_id, use o professor da turma.
i) Na mensagem de confirmação do WhatsApp (dentro de marcar_aula), acrescente
   "\n👨‍🏫 Professor(a): {nome}" quando houver professor resolvido.

--- 4. PORTAL DO ALUNO ---
j) frontend/templates/portal.html linha 254-271: o JS itera `dados.horarios_livres.forEach(hora
   => ...)` tratando cada item como string. Adapte para o novo formato de objeto
   ({hora, grade_id, vagas}), mostre "18:00" no botão (e "2 vagas" discretamente se vagas>1),
   e envie o grade_id junto no formulário oculto de POST /reagendar/{token} (linha ~307).
k) app/routes/portal.py, rota POST /reagendar/{token}: aceite grade_id: Optional[int] = Form(None),
   resolva o professor pelo GradeProfessor, grave em Aula.professor_id e mude a mensagem de
   WhatsApp para "Reposição agendada com o professor {nome}" quando houver professor.

--- 5. PAINEL DO PROFESSOR (frontend) ---
l) index.html: nova aba "Professores" (botão id="btnTabProfessores" + section id="abaProfessores")
   no mesmo padrão Tailwind das outras, com lista + botão de cadastrar.
m) script.js: registre 'professores' em trocarAba(); crie carregarProfessores(),
   abrirModalProfessor() e deletarProfessor() no mesmo estilo de carregarAlunos/abrirModalAluno.
n) script.js, no formulário da aba "Grade Base" (fetch em POST configurar-grade na linha 897 e
   carregarGridSemanal na 858) + index.html form id="formGrade": adicione um <select> de professor
   e um input numérico "Vagas simultâneas" (default 1), e mostre o nome do professor e as vagas
   em cada turno listado no grid semanal.
o) Na aba Agenda (carregarAgenda), exiba o professor de cada aula quando houver.

IMPORTANTE: horários já cadastrados ficam com professor_id NULL e capacidade 1 — o sistema
deve continuar funcionando exatamente como hoje para eles (compatibilidade retroativa).
```

**Ordem de aplicação sugerida ao rodar com o Gemini:** peça primeiro os blocos 1+2 (modelos e
CRUD, com os SQL), rode o `ALTER TABLE`, teste o cadastro de professor. Só depois peça o
bloco 3 (que é onde mora o risco), e por último 4 e 5. Se pedir tudo de uma vez, ele
provavelmente vai reescrever `horarios_livres` inteiro e quebrar o portal.

---

## Sugestões estruturais (quando houver tempo/orçamento)

1. **Alembic** — `pip install alembic && alembic init migrations`, apontar para
   `app.database.Base`, `alembic revision --autogenerate`. Sem isso, cada demanda acima
   exige `ALTER TABLE` na mão no Render.
2. **Unificar `Aula` + `HistoricoAula`** numa única tabela `Aula` com os campos pedagógicos
   (`status_presenca`, `desempenho`, `observacao`, `chamada_realizada`). O P2 é o paliativo;
   isto é a cura. Elimina de uma vez as reclamações 2 e 5.
3. **Camada de serviço** — mover a lógica de negócio das rotas para
   `app/services/agendamento.py`. `aulas.py` tem 545 linhas com regra de negócio, acesso ao
   Google e WhatsApp misturados; `marcar_aula` sozinha tem 120 linhas e prints de debug.
4. **Pydantic em tudo** — várias rotas recebem `dados: dict` cru (`/turmas/`, `/aulas/avulsa`,
   `/token`), sem validação. Use os schemas.
5. **Frontend em módulos** — quebrar `script.js` em `api.js`, `alunos.js`, `turmas.js`,
   `agenda.js`, `relatorios.js` com `<script type="module">`.
6. **Testes** — só existe `tests/test_aulas.py`. Cubra: cancelamento gerando crédito,
   exclusão de turma preservando crédito, limite semanal e conflito de horário.
