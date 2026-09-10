# Migração para YCloud Coexistence

Este procedimento mantém o mesmo número no WhatsApp Business do professor e ativa os
envios automáticos pela API oficial. Não conecte o número real antes de concluir os
passos de preparação e teste.

## 1. Preparação da conta

1. Crie a conta YCloud em nome da empresa/professor que é dono do número.
2. Atualize o WhatsApp Business no celular e faça um backup das conversas.
3. Confirme que o portfólio empresarial da Meta pertence ao cliente, não ao desenvolvedor.
4. No onboarding da YCloud, escolha **WhatsApp Business App Coexistence** e siga o QR
   Code exibido pela Meta.
5. Não desinstale o WhatsApp Business. Abra o aplicativo ao menos uma vez a cada 13 dias.

O onboarding pode desconectar os aparelhos vinculados. Reconecte somente os dispositivos
compatíveis depois da ativação. Broadcast pelo aplicativo, edição/exclusão de mensagem,
mensagens temporárias, visualização única e localização ao vivo podem ficar indisponíveis.
As conversas individuais continuam funcionando no celular.

## 2. Templates de utilidade

Crie os templates abaixo na YCloud, todos na categoria **UTILITY**. Os nomes, idiomas e
a ordem das variáveis precisam coincidir exatamente com esta tabela.

| Nome | Idioma | Corpo sugerido |
|---|---|---|
| `lembrete_aula_1h_v1` | `en_US` | `Hello {{1}}! 👋 Your class starts in 1 hour at {{2}}. Are you ready? ⏰📚` |
| `lembrete_aula_24h_v1` | `pt_BR` | `Olá, {{1}}! Sua aula está marcada para amanhã, {{2}}, às {{3}}. Para consultar ou reagendar, acesse: {{4}}` |
| `link_portal_aluno_v1` | `pt_BR` | `Olá, {{1}}! Aqui está seu link exclusivo do portal de agendamentos: {{2}}. Por lá você pode consultar aulas e agendar reposições.` |
| `aula_agendada_v1` | `pt_BR` | `Olá, {{1}}! Sua aula foi agendada para {{2}} às {{3}}. Tipo: {{4}}. Professor(a): {{5}}.` |
| `aula_reagendada_v1` | `pt_BR` | `Olá, {{1}}! Sua aula foi remarcada para {{2}}. Professor(a): {{3}}.` |
| `aula_cancelada_v1` | `pt_BR` | `Olá, {{1}}! Sua aula de {{2}} foi cancelada. Resultado: {{3}}. Portal: {{4}}` |
| `cancelamento_professor_v1` | `pt_BR` | `Aviso de cancelamento: {{1}} cancelou a aula de {{2}}. Resultado: {{3}}.` |
| `credito_reposicao_vencendo_v1` | `pt_BR` | `Olá, {{1}}! Seu crédito de reposição vence em {{2}}. Agende pelo portal: {{3}}` |
| `lembrete_aula_breve_v1` | `pt_BR` | `Olá, {{1}}! Sua aula começa em breve, às {{2}}. Portal: {{3}}` |

A Meta pode ajustar a categoria ou pedir pequenas mudanças no texto durante a análise.
Se um nome for alterado, configure a variável correspondente no Render em vez de mudar o
código. A aprovação precisa estar concluída antes de ativar `WHATSAPP_PROVIDER=ycloud`.

## 3. Webhook

No painel da YCloud, em **Developers > Webhooks**, cadastre:

```text
https://SEU-DOMINIO-DO-RENDER/webhook/ycloud
```

Ative o evento `whatsapp.message.updated`. Copie o segredo gerado para
`YCLOUD_WEBHOOK_SECRET`. O backend valida a assinatura HMAC antes de aceitar o evento e
ignora automaticamente eventos repetidos.

A auto-resposta de portal fica desligada por padrão para não atrapalhar as conversas
manuais do professor. Só ative `WHATSAPP_AUTO_REPLY_PORTAL=true` e o evento
`whatsapp.inbound_message.received` se esse comportamento for realmente desejado.

## 4. Variáveis no Render

Configure primeiro todas as variáveis sem mudar o provedor:

```text
WHATSAPP_PROVIDER=evolution
YCLOUD_API_URL=https://api.ycloud.com/v2
YCLOUD_API_KEY=...
YCLOUD_PHONE_NUMBER=+55...
YCLOUD_WEBHOOK_SECRET=...
WHATSAPP_AUTO_REPLY_PORTAL=false
```

Os nomes padrão dos templates já estão no código. Use as variáveis
`YCLOUD_TEMPLATE_*` do `.env.example` apenas se os nomes aprovados forem diferentes.

## 5. Banco de dados

Antes do deploy, aplique no PostgreSQL:

```text
migrations/003_rastrear_whatsapp_ycloud.sql
```

A aplicação também cria tabelas ausentes na inicialização, mas a migração explícita deixa
a alteração auditável e evita depender desse comportamento.

## 6. Corte seguro

Os templates do número real só podem ser criados e aprovados depois do onboarding do
WABA/Coexistence. Por isso, faça primeiro os testes disponíveis no canal de teste da
YCloud. Para a troca do número real, escolha um período com poucas aulas e siga a ordem:

1. No Render, defina `WHATSAPP_REMINDERS_ENABLED=false` e aguarde o novo deploy.
2. Confirme que não há lembrete em processamento e faça backup das conversas.
3. Inicie o onboarding do número real em **WhatsApp Business App Coexistence**. Esse
   passo pode desconectar a sessão da Evolution, mas mantém o aplicativo do professor.
4. Crie os templates do número real e aguarde todos ficarem como `APPROVED`. Durante
   essa espera, o professor pode conversar pelo aplicativo, mas os lembretes automáticos
   permanecem pausados.
5. Cadastre e teste o webhook. Faça um envio pela própria YCloud e confirme `delivered`.
6. No Render, troque `WHATSAPP_PROVIDER=ycloud`, mantenha os lembretes pausados e faça
   o deploy.
7. Envie uma notificação controlada e confira `GET /integracoes/whatsapp/status` com o
   login administrativo, validando o ciclo `accepted -> sent -> delivered`.
8. Defina `WHATSAPP_REMINDERS_ENABLED=true`, faça o deploy e teste uma aula marcada a
   pouco mais de uma hora.
9. Teste também uma conversa manual pelo WhatsApp Business do celular.
10. Mantenha a DigitalOcean por alguns dias sem uso. Cancele somente após uma semana sem
    falhas de entrega.

Não mantenha Evolution e YCloud automatizando o mesmo número ao mesmo tempo. Se a
aprovação de templates demorar, envie os lembretes manualmente pelo aplicativo durante a
janela de transição.

## 7. Significado dos estados

- `accepted`: a YCloud aceitou a solicitação, mas o aluno ainda pode não ter recebido.
- `sent`: a mensagem chegou aos sistemas do WhatsApp.
- `delivered`: chegou a um aparelho do destinatário.
- `read`: o destinatário abriu a mensagem, quando a confirmação de leitura está ativa.
- `failed`: houve falha comprovada; o código e a mensagem de erro ficam registrados.
- `desconhecido`: ocorreu uma falha de rede ambígua. O sistema não repete automaticamente
  para evitar que uma resposta perdida gere uma mensagem duplicada.

Cada notificação tem um `external_id` determinístico. Reexecuções do agendador usam o
mesmo ID e não enviam novamente uma mensagem já aceita.
