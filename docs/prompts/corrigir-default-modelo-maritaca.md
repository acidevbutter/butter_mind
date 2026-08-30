Corrija o achado 4 de `docs/auditoria-seguranca-2026-08-29.md` -- o default de `maritaca_model` em
`app/settings/config.py` ficou desatualizado em relação ao `.env.example` desde o commit `e26f9c5`
("update Maritaca model to sabiazinho-4-br-sp in .env.example").

## Contexto

- `app/settings/config.py:17` -- `maritaca_model: str = "sabia-4"`
- `.env.example:14` -- `MARITACA_MODEL=sabiazinho-4-br-sp`

Quem sobe o serviço sem `.env` (setup local rápido, CI, ou uma variável de ambiente faltando em
algum deploy) usa silenciosamente `sabia-4` em vez do modelo pretendido.

## O que fazer

1. Em `app/settings/config.py:17`, altere o default para `"sabiazinho-4-br-sp"`, igualando ao
   `.env.example`.
2. Faça uma varredura por outras ocorrências hardcoded do nome antigo do modelo
   (`grep -rn "sabia-4" --include=*.py app tests docs`) e atualize as que fizerem sentido --
   preste atenção especial a fixtures/factories de teste que possam fixar esse valor.
3. Adicione um teste de regressão simples em `tests/` (ex. em um arquivo de settings, ou junto de
   `tests/core/llm/test_maritaca_provider.py`) que instancia `Settings()` sem `.env` carregado
   (ou com `env_file=None`) e confirma que `maritaca_model` bate com o valor de
   `.env.example` -- para pegar a próxima divergência automaticamente em vez de depender de
   auditoria manual. Se não for prático comparar contra o arquivo `.env.example` em runtime, ao
   menos hard-code o valor esperado (`"sabiazinho-4-br-sp"`) no teste e comente que ele deve ser
   mantido em sincronia com `.env.example`.

## Testes

- Rode o novo teste de regressão e confirme que falha antes da correção (default antigo) e passa
  depois.
- Rode `pytest` completo para garantir que nenhum teste existente dependia do default antigo
  (`"sabia-4"`).
