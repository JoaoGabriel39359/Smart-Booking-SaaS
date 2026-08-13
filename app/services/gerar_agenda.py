from datetime import datetime, timedelta
from app import models
from app.database import SessionLocal 
from app.models import Aluno, HorarioAula, HistoricoAula, Aula, StatusAula # Importamos Aula e StatusAula
from app.services.google_calendar import criar_evento 

def gerar_aulas_da_semana(db=None):
    sessao_local = False
    if db is None:
        db = SessionLocal()
        sessao_local = True
        
    try:
        hoje = datetime.now()
        # Começamos a gerar a partir de hoje para não criar aulas no passado
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        horarios = db.query(HorarioAula).all()

        for semana in range(4):
            deslocamento_dias = semana * 7
            for h in horarios:
                data_alvo = (inicio_semana + timedelta(days=h.dia_da_semana + deslocamento_dias)).date()
                inicio_dt = datetime.combine(data_alvo, h.horario)

                # Pula se a data calculada já passou
                if inicio_dt < hoje:
                    continue

                duracao_aula = 60
                alunos_afetados = []
                nome_para_google = ""
                turma_id_vinculo = None

                if h.turma_id:
                    turma = db.query(models.Turma).filter(models.Turma.id == h.turma_id).first()
                    if turma:
                        nome_para_google = turma.nome_turma
                        duracao_aula = turma.duracao_minutos or 60
                        alunos_afetados = db.query(Aluno).filter(Aluno.turma_id == h.turma_id).all()
                        turma_id_vinculo = turma.id
                else:
                    aluno_vip = db.query(models.Aluno).filter(models.Aluno.id == h.aluno_id).first()
                    if aluno_vip:
                        nome_para_google = f"VIP - {aluno_vip.nome}"
                        alunos_afetados = [aluno_vip]

                if not alunos_afetados: continue

                # --- TRAVA DE DUPLICIDADE (Olha para a tabela Aula) ---
                primeiro_aluno = alunos_afetados[0]
                aula_existente = db.query(Aula).filter(
                    Aula.aluno_id == primeiro_aluno.id,
                    Aula.data_inicio == inicio_dt
                ).first()

                if not aula_existente:
                    fim_dt = inicio_dt + timedelta(minutes=duracao_aula)
                    google_id_atual = None
                    try:
                        g_res = criar_evento(inicio=inicio_dt, fim=fim_dt, nome_aluno=nome_para_google)
                        google_id_atual = g_res[0] if isinstance(g_res, tuple) else g_res
                    except Exception as e:
                        print(f"⚠️ Erro Google: {e}")

                    for aluno in alunos_afetados:
                        # 1. SALVA NA AGENDA (Para o Professor e Portal verem)
                        nova_agenda = Aula(
                            aluno_id=aluno.id,
                            turma_id=turma_id_vinculo,
                            data_inicio=inicio_dt, # DATA + HORA
                            data_fim=fim_dt,
                            status=StatusAula.marcada, # ENUM CORRETO
                            google_event_id=google_id_atual
                        )
                        db.add(nova_agenda)

                        # 2. SALVA NO HISTÓRICO (Para a chamada pedagógica)
                        nova_hist = HistoricoAula(
                            aluno_id=aluno.id,
                            data_aula=inicio_dt.date(), # DATA + HORA
                            status_presenca=False,
                            chamada_realizada=False,
                            observacao=f"Agendamento Mensal - {duracao_aula}min",
                            google_event_id=google_id_atual
                        )
                        db.add(nova_hist)
        
        db.commit()
        print("🚀 Sincronização finalizada com sucesso nas tabelas Aula e Historico!")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao gerar agenda: {e}")
    finally:
        if sessao_local:
            db.close()