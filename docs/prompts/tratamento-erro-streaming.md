Corrija o achado 3 de `docs/auditoria-seguranca-2026-08-29.md` -- `DiagnosisService.stream_message`
não trata falhas do provedor LLM que ocorrem durante o streaming em si, só antes dele. Leia o
documento inteiro antes de começar.

## Contexto

`app/diagnosis/service.py:335-413` (`stream_message`) já converte em evento SSE `{"type":
"error", ...}` as falhas de:

- construção de contexto (`ValidationDomainError`, tratado em `:359-362`);
- checagem de orçamento (`LLMBudgetExceededError`/`LLMPricingUnavailableError`, tratado em
  `:363-365`).

Mas o laço principal:

```python
async for event in self.llm_provider.complete_stream(
    system=system_prompt,
    messages=llm_messages,
    max_tokens=governance.diagnosis_max_output_tokens,
):
```

(linhas 367-374) não está dentro de nenhum `try/except`. Se `MaritacaProvider.complete_stream`
(`app/core/llm/maritaca_provider.py:96-124`) levantar `LLMRateLimitError` ou `LLMProviderError` no
meio da geração (depois de já ter emitido alguns deltas), a exceção sobe crua pelo generator:
nenhum evento `error` é enviado, `add_message` (linha 385) nunca roda, e a resposta parcial do
visitante fica sem réplica persistida.

## O que fazer

1. Envolva o laço `async for event in self.llm_provider.complete_stream(...)` (linhas 367-374) em
   `try/except (LLMRateLimitError, LLMProviderError) as exc`.
2. No `except`, se `full_content` já tiver conteúdo parcial (`full_content` truthy), persista-o
   mesmo assim via `self.repository.add_message(diagnosis_session_id=session_id,
   role="assistant", content=full_content)` -- não descarte uma resposta parcial que o visitante
   já viu chegar via SSE. Marque de alguma forma que a mensagem é parcial/truncada (ex.: um campo
   novo `truncated: bool` em `DiagnosisMessage`/`add_message`, com migration Alembic
   correspondente, ou ao menos anexe um marcador no fim do `content`).
3. Depois de persistir (ou decidir não persistir, se `full_content` estiver vazio), faça
   `yield {"type": "error", "detail": <mensagem amigável, sem stack trace>}` e retorne, no mesmo
   padrão dos outros dois blocos de erro do método.
4. Não silencie a exceção nos logs: capture com `logger.exception` (ou confirme que o
   `@log_errors` de `app/core/decorators.py` já cobre isso no nível do método) antes do `yield`,
   para investigação futura.
5. Atualize a docstring do método (linhas 341-347) para descrever esse terceiro caso de erro, já
   que hoje ela só menciona o cap de turnos.
6. Atualize `app/diagnosis/router.py:91-98` (descrição de `send_message_stream`) e
   `docs/butter-mind-fluxos.md` (linha final da seção 2, que já cita esse gap) para refletir que o
   caso agora tem um contrato definido.

## Testes

Em `tests/diagnosis/` (seguir o estilo de `tests/diagnosis/test_diagnosis_grounding.py`):

- Simule um `LLMProvider.complete_stream` fake que emite 2 deltas e depois levanta
  `LLMProviderError` -- confirme que o stream SSE termina com um evento `{"type": "error", ...}`
  (não uma exceção não tratada) e que a mensagem parcial foi persistida no banco.
- Mesmo cenário com zero deltas emitidos antes da falha -- confirme que nenhuma mensagem vazia é
  persistida.
- Confirme que `LLMUsageService.record` não é chamado quando o provedor falha antes de emitir o
  evento `response.completed` (nenhum uso "fantasma" registrado para uma resposta que não
  terminou).
- Rode `pytest` no módulo `tests/diagnosis` inteiro para garantir que os testes de streaming
  existentes continuam passando.
