BEGIN;

-- Falha de forma segura se o banco ainda contiver aulas ativas duplicadas.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM aulas
    WHERE status = 'marcada'
    GROUP BY aluno_id, data_inicio
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION
      'Existem aulas ativas duplicadas. Revise-as antes de aplicar o índice de proteção.';
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_aulas_aluno_inicio_marcada
  ON aulas (aluno_id, data_inicio)
  WHERE status = 'marcada';

COMMIT;
