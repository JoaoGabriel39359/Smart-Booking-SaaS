from datetime import datetime, timedelta
from app import models
from app.database import SessionLocal # Mantemos para uso manual (main)
from app.models import Aluno, HorarioAula, HistoricoAula
from app.services.google_calendar import criar_evento 

# Adicionamos 'db=None' para que a rota possa "emprestar" a conexão dela para esta função
def gerar_aulas_da_semana(db=None):
    # Se a rota não passou um db, ele abre um novo aqui (para uso manual)
    sessao_local = False
    if db is None:
        db = SessionLocal()
        sessao_local = True
        
    try:
        hoje = datetime.now()
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        horarios = db.query(HorarioAula).all()

        for semana in range(4):
            deslocamento_dias = semana * 7
            for h in horarios:
                data_alvo = (inicio_semana + timedelta(days=h.dia_da_semana + deslocamento_dias)).date()
                inicio_dt = datetime.combine(data_alvo, h.horario)

                # Busca duração e alunos
                duracao_aula = 60
                alunos_afetados = []
                nome_para_google = ""

                if h.turma_id:
                    turma = db.query(models.Turma).filter(models.Turma.id == h.turma_id).first()
                    if turma:
                        nome_para_google = turma.nome_turma
                        duracao_aula = turma.duracao_minutos or 60
                        alunos_afetados = db.query(Aluno).filter(Aluno.turma_id == h.turma_id).all()
                else:
                    aluno_vip = db.query(models.Aluno).filter(models.Aluno.id == h.aluno_id).first()
                    if aluno_vip:
                        nome_para_google = f"VIP - {aluno_vip.nome}"
                        alunos_afetados = [aluno_vip]

                if not alunos_afetados: continue

                # Trava de duplicidade
                primeiro_aluno = alunos_afetados[0]
                aula_existente = db.query(HistoricoAula).filter(
                    HistoricoAula.aluno_id == primeiro_aluno.id,
                    HistoricoAula.data_aula == data_alvo
                ).first()

                if not aula_existente:
                    fim_dt = inicio_dt + timedelta(minutes=duracao_aula)
                    google_id_atual = None
                    try:
                        google_id_atual = criar_evento(inicio=inicio_dt, fim=fim_dt, nome_aluno=nome_para_google)
                    except Exception as e:
                        print(f"⚠️ Erro Google: {e}")

                    for aluno in alunos_afetados:
                        nova_aula = HistoricoAula(
                            aluno_id=aluno.id,
                            data_aula=data_alvo,
                            status_presenca=False,
                            observacao=f"Agendamento Mensal - {duracao_aula}min",
                            google_event_id=google_id_atual
                        )
                        db.add(nova_aula)
        
        db.commit()
        print("🚀 Sincronização finalizada!")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro: {e}")
    finally:
        # Só fecha se foi essa função que abriu. 
        # Se veio da rota (turmas.py), a rota fecha depois.
        if sessao_local:
            db.close()