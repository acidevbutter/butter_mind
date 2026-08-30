# butter_mind — auditoria de segurança e qualidade

Data: 2026-08-29
Escopo: leitura estática de routers, serviços, configuração e testes do serviço `butter_mind` (chat, diagnóstico guiado, orçamento de LLM). Complementa `docs/butter-mind-fluxos.md`.

## Resumo

Cinco achados concretos, priorizados por severidade. Os três primeiros são de segurança; os dois últimos são inconsistência e lacuna de teste. Cada achado tem um prompt de correção correspondente em `docs/prompts/`.

## 1. [SEGURANÇA — Alta] Endpoints de diagnóstico e chat sem autenticação

**Arquivos:** `app/diagnosis/router.py:59` (`create_session`), `:76` (`send_message`), `:100` (`send_message_stream`), `:122` (`submit`); `app/chat/router.py:39,53,67,82,98` (todas as rotas do router).

Nenhuma dessas rotas declara `dependencies=[RequireInternalApiKey]` (padrão já usado em `app/diagnosis/router.py:130,147,163,173,183` para as rotas internas). A descrição de `send_message_stream` (`app/diagnosis/router.py:91-98`) afirma que é um "endpoint interno (chamado apenas pelo devbutter_backend, nunca diretamente pelo navegador)", mas nada no código impõe isso — qualquer chamador com um UUID de sessão/conversa pode ler, escrever ou consumir orçamento de LLM nessas rotas.

## 2. [SEGURANÇA — Média] Race condition no enforcement de orçamento mensal

**Arquivo:** `app/llm_usage/service.py:31-54` (`ensure_budget`), uso em `app/diagnosis/service.py:318-333` (`_complete_reply`), `:356-365` (`stream_message`), `:412-420` (`_extract`), e `app/chat/service.py:49-60,78-90`.

`ensure_budget` lê `monthly_cost` (soma agregada) e compara com `budget.monthly_budget_brl` num SELECT simples, sem lock nem reserva; só depois da chamada ao provedor é que `record()` (linha 56) persiste o gasto real. Duas requisições concorrentes no mesmo `flow` leem o mesmo "gasto até agora", passam ambas na checagem, e só depois de cada uma completar seu turno o gasto é gravado — permitindo ultrapassar `monthly_budget_brl` por chamadas simultâneas. Combinado com o achado 1 (sem autenticação), qualquer cliente externo pode abusar disso e esgotar o orçamento compartilhado do mês para todos os usuários do fluxo.

## 3. [SEGURANÇA/OPEN ITEM — Média] Streaming sem tratamento de erro durante a geração

**Arquivo:** `app/diagnosis/service.py:335-413` (`stream_message`), especificamente o laço `async for event in self.llm_provider.complete_stream(...)` em `:367-374`.

O método só trata exceções antes do laço (context build em `:359-362`, orçamento em `:363-365`, ambos convertidos em `{"type": "error", ...}`). Se o provedor Maritaca falhar durante o streaming (rate limit, erro de rede, timeout), a exceção sobe crua pelo generator: nenhum evento `error` é emitido, a resposta parcial do assistente nunca é persistida (`add_message` só roda depois do laço, em `:385`) e o cliente recebe um SSE truncado sem evento `done`. O contrato de reconexão/cancelamento não existe.

## 4. [INCONSISTÊNCIA — Baixa] Modelo padrão da Maritaca divergente entre config e `.env.example`

**Arquivos:** `app/settings/config.py:17` define `maritaca_model: str = "sabia-4"`; `.env.example:14` define `MARITACA_MODEL=sabiazinho-4-br-sp` (atualizado no commit `e26f9c5`, "update Maritaca model to sabiazinho-4-br-sp in .env.example", sem atualizar o default do `Settings`).

Quem sobe o serviço sem um `.env` (ex.: teste local rápido, ou uma variável faltando) usa silenciosamente um modelo diferente do documentado/pretendido.

## 5. [OPEN ITEM — Baixa] Falta de testes para orçamento e streaming

**Diretório:** `tests/` — existe `tests/llm_usage/test_llm_usage_router.py` (testa só a camada HTTP), mas não há `tests/llm_usage/test_llm_usage_service.py` cobrindo `ensure_budget`/`record` isoladamente, nem teste algum para `DiagnosisService.stream_message` (`app/diagnosis/service.py:335`). As duas funcionalidades descritas nos commits recentes ("enforce monthly LLM budgets by flow", streaming SSE) não têm cobertura de regressão para a race condition (achado 2) nem para a falha de provedor durante o streaming (achado 3).

## Fora de escopo desta rodada

Privacidade/retenção do transcript e do CNPJ (já registrada em `docs/butter-mind-fluxos.md`, seção 2), injeção de prompt via conteúdo recuperado do RAG, e rate limiting por IP/cliente — mencionados aqui apenas como contexto, não convertidos em prompt de correção.
