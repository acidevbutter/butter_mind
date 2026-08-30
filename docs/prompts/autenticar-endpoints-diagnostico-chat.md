Corrija o achado 1 de `docs/auditoria-seguranca-2026-08-29.md` -- as rotas de diagnóstico e chat
voltadas ao público não têm nenhuma autenticação, incluindo o endpoint de streaming que a própria
docstring descreve como "interno". Leia o documento inteiro antes de começar.

## Contexto

`app/diagnosis/router.py` já usa `dependencies=[RequireInternalApiKey]` (definido em
`app/core/dependencies.py::require_internal_api_key`) nas rotas administrativas
(`turn-metrics`, `requests`, `internal/dashboard/*`). As rotas de fluxo do visitante não têm
gate nenhum:

- `app/diagnosis/router.py:59` `create_session`
- `app/diagnosis/router.py:76` `send_message`
- `app/diagnosis/router.py:100` `send_message_stream`
- `app/diagnosis/router.py:122` `submit`
- `app/chat/router.py:39,53,67,82,98` (todas as rotas)

O `send_message_stream` (linhas 91-98 da docstring) afirma ser "endpoint interno (chamado apenas
pelo devbutter_backend, nunca diretamente pelo navegador)" -- isso precisa virar enforcement real,
não só comentário.

## O que fazer

1. Não reaproveite `RequireInternalApiKey` para as rotas de visitante (`create_session`,
   `send_message`, `submit`, e as rotas de chat) -- essa chave é para o pequeno público interno
   (dashboard/CRM), não para o tráfego público do site. Em vez disso:
   - Adicione um novo gate `require_service_api_key` em `app/core/dependencies.py`, seguindo o
     mesmo padrão de `require_internal_api_key` (header dedicado, ex. `X-Service-Api-Key`,
     comparado contra uma nova setting `service_api_key` em `app/settings/config.py`, com
     `raise NotFoundError("Not found")` quando ausente/errado -- mesmo fail-closed já usado).
   - Documente no docstring do novo gate que ele identifica "chamadas vindas do
     devbutter_backend", distinto do `internal_api_key` (que identifica humano/dashboard).
2. Aplique `dependencies=[RequireServiceApiKey]` em `send_message_stream`
   (`app/diagnosis/router.py:100`), já que a própria descrição da rota assume esse contrato.
3. Para `create_session`, `send_message` e `submit` (linhas 59, 76, 122) e todas as rotas de
   `app/chat/router.py`, aplique o mesmo `RequireServiceApiKey` -- essas rotas hoje aceitam
   qualquer chamador que descubra um UUID de sessão/conversa.
4. Adicione `SERVICE_API_KEY=` em `.env.example` (mesmo padrão de `INTERNAL_API_KEY`, comentário
   explicando o propósito) e o campo correspondente em `app/settings/config.py`.
5. Atualize `docs/butter-mind-fluxos.md` -- as seções 1 e 2 ("Falhas/lacunas") citam
   explicitamente a ausência de autenticação; ajuste o texto para refletir o novo gate.

## Testes

- Em `tests/diagnosis/test_diagnosis_router.py` e `tests/chat/test_chat_router.py`: adicione um
  teste por rota afetada confirmando 404 (padrão do `NotFoundError` fail-closed) sem o header
  `X-Service-Api-Key`, e sucesso com o header correto.
- Confirme que as rotas já protegidas por `RequireInternalApiKey`
  (`turn-metrics`, `requests`, `internal/dashboard/*`) continuam funcionando sem o novo header --
  os dois gates são independentes.
- Rode a suíte completa (`pytest`) para garantir que nenhum teste existente dependia do
  comportamento sem autenticação.
