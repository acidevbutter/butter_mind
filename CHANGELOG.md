# Changelog

## [Unreleased]

- Removido `--reload` da imagem Docker para execução em produção.

- Documentados os fluxos existentes, pontos fortes, falhas e lacunas do serviço em Markdown e Mermaid.
- Adicionados dashboard interno e overrides persistidos para limites do diagnóstico.
- Migradas as chamadas da Maritaca para a Responses API, com cache de prompt,
  tokens cacheados e uso final em streaming.
- Adicionados limites financeiros mensais e telemetria de custo por fluxo de LLM.
