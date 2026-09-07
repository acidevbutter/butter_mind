# Mind API — especificação de navegação

**Dono:** chat, fluxo de Cotação IA/diagnóstico, base de conhecimento e
orçamento de LLM. Contrato de campos e respostas: `/openapi.json` da instância.

## Acesso

- Rotas de chat e diagnóstico público exigem `X-Service-Api-Key`. Sem chave
  válida a resposta é 404 propositalmente (fail-closed).
- Rotas `/knowledge/*`, `/llm-usage/internal/*` e dashboard interno exigem
  `X-Internal-Api-Key`.
- Essas chaves são distintas e nunca devem chegar ao navegador.

## Rotas por domínio

| Prefixo | Operações | Módulo a abrir |
| --- | --- | --- |
| `/chat/conversations` | criar, buscar, listar/enviar mensagens | `app/chat/` |
| `/chat/generate` | geração textual sem persistir conversa | `app/chat/` |
| `/diagnosis/sessions` | criar sessão; mensagens normal/SSE; selecionar opção; perfil; submit; métricas de turno | `app/diagnosis/` |
| `/diagnosis/requests` | listar leads extraídos | `app/diagnosis/` |
| `/diagnosis/internal/dashboard` | overview e leitura/alteração de limites seguros | `app/diagnosis/` |
| `/knowledge/sources` | criar fonte e iniciar ingestão | `app/knowledge/` |
| `/llm-usage/internal` | resumo mensal e leitura/alteração de budget por fluxo | `app/llm_usage/` |

`GET /health` prova processo; `GET /health/ready` verifica banco.

## Regras de integração

- O fluxo de diagnóstico produz preview estruturado; o Platform espelha o
  resultado e é o único dono de cotações/pedidos.
- O schema compartilhado de estado de conversa é
  `contracts/conversation_state.schema.json`; gere-o pelo script já existente,
  não copie a forma para outro serviço.
- `POST .../messages/stream` é SSE; preserve o streaming, métricas e limites
  antes de alterar o fluxo.

## Onde mudar

Abra primeiro `app/<domínio>/router.py` e `schemas.py`; o domínio segue
`models.py`, `repository.py`, `service.py`, `router.py`, `dependencies.py`.
Providers LLM/embeddings ficam em `app/core/`, não nos routers.
