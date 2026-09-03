from datetime import datetime, timedelta
from app import models
from app.database import SessionLocal 
from app.models import Aluno, HorarioAula, HistoricoAula, Aula, StatusAula # Importamos Aula e StatusAula
from app.services.google_calendar import criar_evento 
from app.core.config import agora_br

def gerar_aulas_da_semana(db=None):
    sessao_local = False
    if db is None:
        db = SessionLocal()
        sessao_local = True
        
    try:
        hoje = agora_br()
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

                professor_id_vinculo = None
                if h.turma_id:
                    turma = db.query(models.Turma).filter(models.Turma.id == h.turma_id).first()
                    if turma:
                        nome_para_google = turma.nome_turma
                        duracao_aula = turma.duracao_minutos or 60
                        alunos_afetados = db.query(Aluno).filter(Aluno.turma_id == h.turma_id).all()
                        turma_id_vinculo = turma.id
                        professor_id_vinculo = turma.professor_id
                else:
                    aluno_vip = db.query(models.Aluno).filter(models.Aluno.id == h.aluno_id).first()
                    if aluno_vip:
                        nome_para_google = f"VIP - {aluno_vip.nome}"
                        alunos_afetados = [aluno_vip]

                if not alunos_afetados: continue

                # --- TRAVA DE DUPLICIDADE (por ALUNO, nao apenas pelo primeiro da turma) ---
                # Antes olhavamos so alunos_afetados[0]: se ele ja tinha a aula, os alunos
                # recem-adicionados na turma NUNCA recebiam agendamento.
                ids_afetados = [a.id for a in alunos_afetados]
                aulas_existentes = db.query(Aula).filter(
                    Aula.aluno_id.in_(ids_afetados),
                    Aula.data_inicio == inicio_dt
                ).all()
                ids_com_aula = {a.aluno_id for a in aulas_existentes}
                alunos_faltantes = [a for a in alunos_afetados if a.id not in ids_com_aula]

                if alunos_faltantes:
                    fim_dt = inicio_dt + timedelta(minutes=duracao_aula)

                    # Reaproveita o evento do Google que a turma ja tem neste horario,
                    # em vez de criar um evento duplicado no calendario.
                    google_id_atual = next(
                        (a.google_event_id for a in aulas_existentes if a.google_event_id), None
                    )
                    if not google_id_atual:
                        try:
                            g_res = criar_evento(inicio=inicio_dt, fim=fim_dt, nome_aluno=nome_para_google)
                            google_id_atual = g_res[0] if isinstance(g_res, tuple) else g_res
                        except Exception as e:
                            print(f"⚠️ Erro Google: {e}")

                    for aluno in alunos_faltantes:
                        # 1. SALVA NA AGENDA (Para o Professor e Portal verem)
                        nova_agenda = Aula(
                            aluno_id=aluno.id,
                            turma_id=turma_id_vinculo,
                            professor_id=professor_id_vinculo,
                            data_inicio=inicio_dt, # DATA + HORA
                            data_fim=fim_dt,
                            status=StatusAula.marcada, # ENUM CORRETO
                            google_event_id=google_id_atual
                        )
                        db.add(nova_agenda)
                        db.flush()

                        # 2. SALVA NO HISTÓRICO (Para a chamada pedagógica)
                        nova_hist = HistoricoAula(
                            aula_id=nova_agenda.id,
                            aluno_id=aluno.id,
                            data_aula=inicio_dt, # DATA + HORA
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