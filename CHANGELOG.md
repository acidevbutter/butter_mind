# Changelog

## [Unreleased]

- Adicionada `docs/API_SPEC.md`: mapa de rotas, chaves de serviço/interna e
  contratos de integração do Mind.

- Fluxo Cotação IA — contrato do preview em fonte única (ADR-0005, parcial):
  `contracts/conversation_state.schema.json` é o JSON Schema do
  `DiagnosisPreview`, regenerado por `scripts/export_conversation_schema.py`;
  `tests/diagnosis/test_conversation_state_contract.py` falha se defasar. O
  `devbutter_backend` parou de redeclarar essa forma (agora relaia o dict cru).
- `DiagnosisPreview.field_options` (novo): catálogo `_OPTION_CATALOG` de
  `services_of_interest` / `budget_range` / `timeline` como `[{id,label}]` em
  todo preview, para o chat renderizar a etapa de review sem cópia hardcoded que
  dessincroniza.
- `DIAGNOSIS_SYSTEM_PROMPT` não cita mais nomes de pessoas da equipe
  ("revisão do time da DevButter"; "Nunca cite nomes de pessoas da equipe").
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
