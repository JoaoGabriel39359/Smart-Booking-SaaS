BEGIN;

CREATE TABLE IF NOT EXISTS mensagens_whatsapp (
  id SERIAL PRIMARY KEY,
  external_id VARCHAR(180) NOT NULL UNIQUE,
  provider VARCHAR(30) NOT NULL DEFAULT 'desconhecido',
  provider_message_id VARCHAR(180),
  wamid VARCHAR(255),
  tipo VARCHAR(80) NOT NULL,
  template_nome VARCHAR(160),
  destinatario VARCHAR(30) NOT NULL,
  aluno_id INTEGER REFERENCES alunos(id) ON DELETE SET NULL,
  aula_id INTEGER REFERENCES aulas(id) ON DELETE SET NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'processando',
  tentativas INTEGER NOT NULL DEFAULT 0,
  erro_codigo VARCHAR(100),
  erro_mensagem VARCHAR(1000),
  criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  aceito_em TIMESTAMP WITHOUT TIME ZONE,
  enviado_em TIMESTAMP WITHOUT TIME ZONE,
  entregue_em TIMESTAMP WITHOUT TIME ZONE,
  lido_em TIMESTAMP WITHOUT TIME ZONE,
  falhou_em TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_external_id
  ON mensagens_whatsapp (external_id);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_provider_message_id
  ON mensagens_whatsapp (provider_message_id);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_wamid
  ON mensagens_whatsapp (wamid);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_tipo
  ON mensagens_whatsapp (tipo);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_destinatario
  ON mensagens_whatsapp (destinatario);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_aluno_id
  ON mensagens_whatsapp (aluno_id);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_aula_id
  ON mensagens_whatsapp (aula_id);
CREATE INDEX IF NOT EXISTS ix_mensagens_whatsapp_status
  ON mensagens_whatsapp (status);

CREATE TABLE IF NOT EXISTS eventos_webhook_whatsapp (
  event_id VARCHAR(180) PRIMARY KEY,
  event_type VARCHAR(100) NOT NULL,
  recebido_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_eventos_webhook_whatsapp_event_type
  ON eventos_webhook_whatsapp (event_type);

COMMIT;
