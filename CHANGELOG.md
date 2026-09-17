# Changelog

## [Unreleased]

- Observabilidade HTTP normalizada: logs de request agora são JSON estruturado
  (`app/settings/logging_config.JsonFormatter`), com um único evento
  `request_completed`/`request_failed` por requisição emitido por
  `RequestContextMiddleware` (antes, requisições com exceção geravam dois
  logs — `logger.exception` + o log final — e o access log do uvicorn
  duplicava o mesmo evento). `uvicorn.access` foi silenciado
  (`WARNING`, `propagate=False`). Campos: `timestamp`, `level`, `logger`,
  `event`, `service`, `environment`, `request_id`, `method`, `route`
  (template da rota; path bruto só quando não casa nenhuma rota),
  `status_code`, `duration_ms`. Sem novas dependências — o EMF via
  `app/core/metrics.py` continua como estava (dimensões já eram
  low-cardinality; `request_id` permanece exclusivo do log).
- Conexão Postgres passa a ser `DATABASE_HOST` / `PORT` / `USER` / `PASSWORD` /
  `NAME`; o Pydantic monta `postgresql+asyncpg://`. `DATABASE_URL` residual
  impede o boot fora de development.

- Cotação IA: `ready` exige e-mail (e problema + serviço) além do perfil;
  `_sanitize_options` marca `recommended` na opção efetivamente mantida;
  `options_snapshot` é limpo ao voltar para `qualifying`.
- Fluxo Cotação IA turno 2 (ADR-0004): `DiagnosisSession` passa a ter estado
  (`stage`, `business_profile`, `selected_option_key`, `options_snapshot`);
  a extração propõe 2-3 `ProductOption` precificadas (faixa/prazo em texto);
  `stage` (`qualifying`→`choosing`→`collecting`→`ready`) é computado no servidor;
  novos `POST /diagnosis/sessions/{id}/select-option` (409 p/ chave fora das
  propostas) e `PATCH /diagnosis/sessions/{id}/business-profile`; `submit` aceita
  overrides de opção/perfil e valida `stage == "ready"`; `DiagnosisRequest`
  carrega `selected_option_key` + `business_profile`. Uma migração
  (`c9a1d3e5b7f2`). `EXTRACTION_PROMPT_VERSION` → `2026-09-02-product-options`.
- `DiagnosisExtraction`/`BusinessProfile` ganham `city` e `business_metrics`
  (0-4 stat cards `{label, value, computed}`) para o dossiê ao vivo da Cotação
  IA (canvas tela 2a); `EXTRACTION_SYSTEM_PROMPT` instruído a nunca inventar
  número e a marcar `computed=true` só para figuras derivadas;
  `EXTRACTION_PROMPT_VERSION` → `2026-09-02-business-metrics`. Sem migração
  (campos só de preview). Ver `docs/architecture/adr-0003-fluxo-cotacao-dossie-portal.md`.
- Removido `--reload` da imagem Docker para execução em produção.

- Documentados os fluxos existentes, pontos fortes, falhas e lacunas do serviço em Markdown e Mermaid.
- Adicionados dashboard interno e overrides persistidos para limites do diagnóstico.
- Migradas as chamadas da Maritaca para a Responses API, com cache de prompt,
  tokens cacheados e uso final em streaming.
- Adicionados limites financeiros mensais e telemetria de custo por fluxo de LLM.
