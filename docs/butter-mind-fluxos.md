# butter_mind — fluxos existentes e pontos de atenção

Data: 2026-08-28  
Escopo: leitura estática do checkout atual, routers, serviços, modelos, migrações e testes.

## Leitura rápida

O serviço expõe quatro grupos de fluxo:

1. chat persistente e geração de texto sem estado;
2. diagnóstico guiado, grounding/RAG, extração estruturada e criação de lead;
3. cadastro e ingestão interna da base de conhecimento;
4. governança interna de limites, custos e métricas.

O desenho tem boas fronteiras entre domínio, persistência, provedor LLM e embeddings. Os principais riscos estão nas fronteiras de identidade/autorização, concorrência e consistência, privacidade do transcript e operação da base de conhecimento.

## Diagrama geral

Ver [`diagrams/butter-mind-visao-geral.mmd`](diagrams/butter-mind-visao-geral.mmd).

## 1. Chat geral

### Fluxo observado

`POST /chat/conversations` cria a conversa. `POST /chat/conversations/{id}/messages` valida a existência, persiste a mensagem do visitante, carrega o histórico completo, consulta o orçamento, chama `LLMProvider.complete`, registra uso e persiste a resposta do assistente. `GET` permite recuperar conversa e mensagens. `POST /chat/generate` usa o mesmo serviço para uma geração avulsa, sem persistência de conversa.

Ver [`diagrams/butter-mind-chat.mmd`](diagrams/butter-mind-chat.mmd).

### Pontos fortes

- O domínio depende do protocolo `LLMProvider`, não da implementação Maritaca.
- A resposta e o uso de tokens são persistidos no chat.
- O orçamento é verificado antes da chamada ao provedor.
- Erros de domínio e do provedor têm tradução HTTP centralizada.

### Falhas/lacunas

- ~~Não há autenticação ou autorização por `session_id`/`conversation_id` no serviço.~~ Corrigido: as rotas de `app/chat/router.py` agora exigem o header `X-Service-Api-Key` (`RequireServiceApiKey`, ver `app/core/dependencies.py`). Isso autentica o chamador (devbutter_backend), não o dono da conversa -- ainda não há autorização por `conversation_id` entre conversas diferentes de visitantes.
- O histórico completo cresce sem limite por requisição; o limite de janela existe no diagnóstico, não no chat geral.
- Não há idempotência para reenvio de mensagem. Retries podem duplicar a mensagem e chamadas ao LLM.
- `generate` aceita `context` livre e não mostra limite de payload, rate limit ou controle de abuso no código observado.
- Não há rota de exclusão, retenção ou anonimização de conversas.

## 2. Diagnóstico guiado e lead

### Fluxo observado

`POST /diagnosis/sessions` abre uma sessão. Cada `POST /diagnosis/sessions/{id}/messages`:

1. conta turnos e aplica `diagnosis_max_turns`;
2. persiste a mensagem do visitante;
3. busca chunks por embedding e limiar configurado;
4. monta prompt grounded e janela recente do histórico;
5. verifica orçamento e chama o LLM para a resposta;
6. persiste resposta e métricas de grounding/tokens;
7. faz uma segunda chamada estruturada para extração e devolve preview/`ready_to_submit`.

Há também a variante SSE `/messages/stream`, que envia deltas e termina com `done`. `POST /submit` reprocessa o transcript completo, exige problema, serviço, nome e e-mail, cria `DiagnosisRequest`, marca a sessão como `completed` e sinaliza `possibly_ungrounded` quando nenhum turno recuperou chunks.

Ver [`diagrams/butter-mind-diagnostico.mmd`](diagrams/butter-mind-diagnostico.mmd).

### Pontos fortes

- O fluxo separa resposta conversacional de extração estruturada.
- Há limite de turnos, limite de saída, janela de histórico e orçamento por fluxo.
- O grounding vazio é exposto como sinal operacional, sem ser apresentado como prova de factualidade.
- A submissão exige campos mínimos e possui restrição única por sessão.
- O SSE trata o limite de turnos/orçamento como evento de erro após o início da resposta.
- Testes cobrem fluxo guiado, streaming, submissão duplicada, grounding, janela e limites.

### Falhas/lacunas e atenção

- ~~A sessão não tem vínculo verificável com visitante, conta, origem ou autorização.~~ Corrigido: `create_session`, `send_message`, `send_message_stream` e `submit` em `app/diagnosis/router.py` agora exigem `X-Service-Api-Key` (mesmo gate do chat). Isso confirma que a chamada vem do devbutter_backend; ainda não distingue visitantes entre si dentro desse contrato.
- A mensagem do visitante é confirmada antes da chamada LLM; falha do provedor deixa sessão parcialmente gravada. O mesmo ocorre se a extração posterior falhar.
- O contador de turnos e a criação do lead não são operações idempotentes de ponta a ponta. Requisições concorrentes podem ultrapassar o limite ou executar chamadas caras duplicadas antes da restrição única agir.
- `submit` persiste o lead e só depois marca a sessão como concluída. A fronteira entre as duas operações não é transacional como uma unidade de negócio.
- O transcript integral é salvo em `raw_transcript_snapshot`, junto com dados de contato; faltam política de retenção, minimização, mascaramento e controle de acesso detalhado.
- `possibly_ungrounded` é um indicador de sessão sem retrieval, não validação de cada afirmação, fonte ou citação.
- O prompt injeta conteúdo recuperado sem evidência de versionamento, confiabilidade da fonte ou defesa explícita contra instruções maliciosas armazenadas na base.
- No streaming, uma falha do provedor depois de alguns deltas pode deixar a mensagem do visitante salva sem resposta persistida; o contrato de reconexão/cancelamento não está definido.
- Não há evidência neste serviço de entrega do lead para CRM, e-mail ou outro consumidor; `list_requests` é apenas leitura interna.

## 3. Base de conhecimento

### Fluxo observado

Com a chave interna, `POST /knowledge/sources` cria uma fonte. `POST /knowledge/sources/{id}/ingest` valida a fonte, divide o texto em blocos fixos de 2.000 caracteres com sobreposição de 200, gera embeddings localmente e insere chunks. Durante o diagnóstico, a busca gera o embedding da consulta e procura chunks similares.

Ver [`diagrams/butter-mind-knowledge.mmd`](diagrams/butter-mind-knowledge.mmd).

### Pontos fortes

- Ingestão e retrieval estão encapsulados em serviço/repositório próprios.
- Embeddings são abstraídos por protocolo e carregados sob demanda.
- A chave interna é fail-closed quando não configurada.
- O score e os chunks recuperados são registrados por turno.

### Falhas/lacunas e atenção

- Chunking é fixo por caracteres e pode cortar estrutura, tabelas, código ou contexto semântico.
- Não há fluxo de atualização, substituição atômica, exclusão, versionamento, checksum ou status de ingestão da fonte.
- Reingerir a mesma fonte pode conflitar em `(source_id, chunk_index)`; não há operação explícita de refresh.
- O modelo de embedding e sua dimensão são configuração/migração acopladas; trocar o modelo exige reindexação coordenada.
- O modelo declara ausência de índice HNSW/IVFFlat; em volume maior, a busca tende a degradar.
- Não há validação visível de tamanho, formato, encoding, origem ou conteúdo dos documentos.
- A busca retorna chunks acima do limiar, mas não há avaliação offline de recall/precisão nem citação verificável no texto gerado.

## 4. Governança, custos e operação interna

### Fluxo observado

As rotas `/llm-usage/internal/*` e `/diagnosis/internal/dashboard/*` usam `X-Internal-Api-Key`. O serviço calcula um custo máximo antes da chamada, registra o custo observado depois, agrega resumo mensal e permite alterar limites seguros do diagnóstico em runtime. O middleware registra contexto de request e CORS é configurado por settings.

Ver [`diagrams/butter-mind-governanca.mmd`](diagrams/butter-mind-governanca.mmd).

### Pontos fortes

- Orçamento separado por fluxo (`general_chat`, `site_text_generation`, `diagnosis_chat`, `diagnosis_extraction`).
- Métricas estruturadas de tokens, cache, grounding e modelo.
- Configurações de diagnóstico têm validação de faixa via Pydantic.
- Endpoints internos falham fechado sem chave configurada.
- O dashboard distingue turnos sem uso de tokens e sessões possivelmente sem grounding.

### Falhas/lacunas e atenção

- Uma chave compartilhada não oferece identidade individual, rotação, escopo, auditoria de operador ou rate limit.
- `ensure_budget` lê o gasto e a chamada ocorre depois; sem reserva/lock, requisições concorrentes podem consumir acima do teto.
- O custo depende de tabela local de pricing e pode ficar indisponível/desatualizado; isso precisa de alerta e procedimento de atualização.
- Não há rota de health/readiness que valide banco, Maritaca, pgvector ou modelo de embeddings; `/health` apenas retorna `ok`.
- O dashboard agrega dados, mas não há retenção, alertas, tracing ou correlação operacional descritos neste serviço.

## Prioridade recomendada

### P0 — antes de exposição ampliada

1. Vincular sessões/conversas a identidade ou capability token com escopo, expiração e autorização.
2. Definir idempotência e transação para turnos, streaming e submissão de lead.
3. Proteger transcript e dados de contato com acesso mínimo, retenção e minimização explícitos.

### P1 — robustez operacional

1. Criar refresh/versionamento da base, validação de fontes e índice vetorial.
2. Adicionar reserva atômica de orçamento, rate limits e auditoria da chave interna.
3. Implementar readiness/dependências, alertas e contrato de falha/reconexão do SSE.

### P2 — qualidade do produto

1. Medir retrieval e respostas com conjunto de avaliação.
2. Melhorar chunking e incluir citações/fontes quando apropriado.
3. Formalizar handoff do lead, estados de processamento e exclusão/anonimização.

## Limites da verificação

Este documento é um mapa estático do código e dos testes presentes neste checkout. Não prova execução integrada com PostgreSQL/pgvector, Maritaca, modelo de embeddings, frontend, proxy ou produção. Também não é uma auditoria visual de telas: este repositório é um backend FastAPI e não contém a interface do visitante.

