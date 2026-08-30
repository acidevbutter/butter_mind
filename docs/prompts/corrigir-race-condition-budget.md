Corrija o achado 2 de `docs/auditoria-seguranca-2026-08-29.md` -- o enforcement de orçamento
mensal por `flow` em `app/llm_usage/service.py` tem uma race condition clássica de
leia-depois-escreva (TOCTOU) que permite ultrapassar `monthly_budget_brl` com chamadas
concorrentes. Leia o documento inteiro antes de começar.

## Contexto

`LLMUsageService.ensure_budget` (`app/llm_usage/service.py:31-54`) faz:

1. `spent = await self.repository.monthly_cost(flow=flow, start=start, end=end)` (linha ~49,
   um `SELECT SUM(...)` simples via `app/llm_usage/repository.py::monthly_cost`);
2. compara `spent + maximum_cost > budget.monthly_budget_brl` (linha 53) e levanta
   `LLMBudgetExceededError` se estourar.

O gasto real só é persistido depois, em `record()` (`app/llm_usage/service.py:56-63`), chamado
pelos callers (`app/diagnosis/service.py:318-333`, `:356-365`, `:412-420`;
`app/chat/service.py:49-60,78-90`) só *depois* de a chamada ao provedor LLM terminar. Duas
requisições concorrentes no mesmo `flow` leem o mesmo `spent` antes de qualquer uma delas gravar o
seu evento, então ambas passam na checagem mesmo que juntas estourem o orçamento.

## O que fazer

1. Adicione uma tabela/coluna de "reserva" por flow-mês em `app/llm_usage/models.py`
   (`LLMBudgetLimit`), ex. `reserved_cost_brl: Mapped[Decimal]` zerada no início de cada mês, com
   uma migration Alembic nova (seguir o padrão de
   `app/alembic/versions/20260824_0300_add_llm_usage_budgets.py`).
2. Em `app/llm_usage/repository.py`, adicione um método `reserve_budget(*, flow, month_start,
   amount) -> bool` que faz o incremento e a checagem **numa única instrução SQL condicional**
   (`UPDATE ... SET reserved_cost_brl = reserved_cost_brl + :amount WHERE flow = :flow AND
   monthly_cost + reserved_cost_brl + :amount <= monthly_budget_brl RETURNING true`, ou
   equivalente com `SELECT ... FOR UPDATE` dentro da mesma transação) para eliminar a janela entre
   leitura e escrita. Prefira a expressão atômica de UPDATE a um lock explícito, para não segurar
   conexões sob carga.
3. Reescreva `LLMUsageService.ensure_budget` (`app/llm_usage/service.py:31-54`) para chamar esse
   método atômico em vez de `monthly_cost` + comparação em Python. Se a reserva falhar, levante
   `LLMBudgetExceededError` como hoje.
4. Ajuste `record()` (`app/llm_usage/service.py:56-63`) para, além de gravar o `LLMUsageEvent`,
   liberar/ajustar a reserva correspondente (a reserva usava `maximum_cost_brl`, o evento real usa
   `actual_cost_brl` -- decremente a reserva pelo valor reservado e credite o gasto real, para não
   deixar "sobra" de orçamento presa até o fim do mês).
5. Trate também a falha do provedor: se `ensure_budget` reservar e a chamada ao LLM falhar antes
   de `record()` rodar, a reserva precisa ser liberada (envolva a chamada num `try/finally` ou
   `try/except` nos três call sites de `_complete_reply`, `stream_message` e `_extract` em
   `app/diagnosis/service.py`, e nos dois em `app/chat/service.py`).

## Testes

- Teste unitário em `tests/llm_usage/` (crie `test_llm_usage_service.py` se não existir) que
  dispara `asyncio.gather` com N chamadas concorrentes de `ensure_budget` para o mesmo `flow`,
  cada uma custando perto do limite do orçamento, e confirma que no máximo o número esperado
  passa (nenhuma execução excede `monthly_budget_brl` na soma).
- Teste confirmando que uma falha do provedor libera a reserva (chame `ensure_budget`, simule
  exceção antes de `record`, e verifique que uma chamada subsequente não é bloqueada por uma
  reserva "presa").
- Rode `pytest`, `ruff check` e `mypy` no módulo `app/llm_usage` antes de considerar concluído.
