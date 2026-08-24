import json
import uuid
from collections.abc import AsyncIterator
from typing import cast

from app.core.decorators import log_errors
from app.core.exceptions import ValidationDomainError
from app.core.llm.exceptions import LLMBudgetExceededError, LLMPricingUnavailableError
from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import LLMMessage, LLMResponse
from app.diagnosis.models import (
    DiagnosisMessage,
    DiagnosisRequest,
    DiagnosisSession,
    DiagnosisTurnMetrics,
)
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.schemas import (
    DiagnosisExtraction,
    DiagnosisGovernanceRead,
    DiagnosisGovernanceUpdate,
    DiagnosisModelUsageRead,
    DiagnosisPreview,
    DiagnosisSessionCreate,
    MindDashboardOverviewRead,
)
from app.knowledge.models import KnowledgeChunk
from app.knowledge.service import KnowledgeIngestionService
from app.llm_usage.service import LLMUsageService
from app.settings.config import settings

DIAGNOSIS_SYSTEM_PROMPT = (
    "Você é o assistente de diagnóstico da DevButter, um estúdio de tecnologia que combina "
    "engenharia, ciência e criatividade para construir produtos de software e IA sob medida. "
    "Sua função é conversar em português do Brasil com visitantes do site para entender o "
    "problema ou a necessidade deles, explicar como a DevButter pode ajudar (agentes de IA, "
    "plataformas web, automações e produtos digitais sob medida), e reunir informações "
    "suficientes para montar um pedido de diagnóstico/orçamento: resumo do problema, serviços "
    "de interesse, faixa de orçamento (se o visitante quiser compartilhar) e prazo desejado. "
    "Além do escopo, você também precisa descobrir, no fluxo natural da conversa (não como um "
    "formulário separado, mas quando fizer sentido, por exemplo perto do fim, ao explicar que vai "
    "preparar o orçamento): o nome do visitante, seu e-mail (obrigatório, é como o orçamento será "
    "entregue), e opcionalmente telefone, nome da empresa e CNPJ/CPF. Nome e e-mail são "
    "indispensáveis antes de encerrar a conversa; os demais são opcionais e podem ficar em aberto. "
    "Seja cordial, faça uma pergunta de cada vez, e não invente informações que o visitante "
    "não deu."
)

GROUNDING_INSTRUCTION = (
    "Use as informações reais abaixo, extraídas da base de conhecimento da DevButter, como "
    "fonte de verdade para preços, prazos e serviços. Se a pergunta do visitante não for "
    "coberta por elas, diga com honestidade que você não tem essa informação específica em "
    "vez de inventar um valor ou prazo."
)

EXTRACTION_SYSTEM_PROMPT = (
    "Analise a conversa entre um visitante e o assistente de diagnóstico da DevButter. "
    "Extraia os campos estruturados pedidos: resumo do problema, serviços de interesse, faixa de "
    "orçamento, prazo, e os dados de contato que o visitante tiver compartilhado (contact_name, "
    "contact_email, contact_phone, company_name, cnpj) -- extraia-os exatamente como o visitante "
    "escreveu, sem inventar ou completar dados que não foram ditos. Marque ready_to_submit=true "
    "somente se já houver informação suficiente para descrever o problema do visitante, ao menos "
    "um serviço de interesse, E contact_name e contact_email; caso qualquer um desses falte, "
    "ready_to_submit=false."
)


def _build_grounded_system_prompt(chunks: list[KnowledgeChunk]) -> str:
    if not chunks:
        return DIAGNOSIS_SYSTEM_PROMPT
    context = "\n\n".join(f"- {chunk.content}" for chunk in chunks)
    return f"{DIAGNOSIS_SYSTEM_PROMPT}\n\n{GROUNDING_INSTRUCTION}\n\n{context}"


@log_errors
class DiagnosisService:
    def __init__(
        self,
        repository: DiagnosisRepository,
        llm_provider: LLMProvider,
        knowledge_service: KnowledgeIngestionService,
        llm_usage_service: LLMUsageService,
    ):
        self.repository = repository
        self.llm_provider = llm_provider
        self.knowledge_service = knowledge_service
        self.llm_usage_service = llm_usage_service

    async def create_session(self, payload: DiagnosisSessionCreate) -> DiagnosisSession:
        return await self.repository.create_session(payload)

    async def get_session(self, session_id: uuid.UUID) -> DiagnosisSession:
        return await self.repository.get_session(session_id)

    async def list_messages(self, session_id: uuid.UUID) -> list[DiagnosisMessage]:
        return await self.repository.list_messages(session_id)

    async def list_turn_metrics(self, session_id: uuid.UUID) -> list[DiagnosisTurnMetrics]:
        return await self.repository.list_turn_metrics(session_id)

    async def get_governance(self) -> DiagnosisGovernanceRead:
        override = await self.repository.get_runtime_settings()
        return DiagnosisGovernanceRead(
            diagnosis_max_output_tokens=(
                override.diagnosis_max_output_tokens
                if override
                else settings.diagnosis_max_output_tokens
            ),
            diagnosis_max_history_messages=(
                override.diagnosis_max_history_messages
                if override
                else settings.diagnosis_max_history_messages
            ),
            diagnosis_max_turns=(
                override.diagnosis_max_turns if override else settings.diagnosis_max_turns
            ),
            diagnosis_grounding_top_k=(
                override.diagnosis_grounding_top_k
                if override
                else settings.diagnosis_grounding_top_k
            ),
            diagnosis_grounding_min_score=(
                override.diagnosis_grounding_min_score
                if override
                else settings.diagnosis_grounding_min_score
            ),
            uses_runtime_override=override is not None,
            maritaca_model=settings.maritaca_model,
            embeddings_model_name=settings.embeddings_model_name,
        )

    async def update_governance(
        self, payload: DiagnosisGovernanceUpdate
    ) -> DiagnosisGovernanceRead:
        await self.repository.save_runtime_settings(**payload.model_dump())
        return await self.get_governance()

    async def dashboard_overview(self) -> MindDashboardOverviewRead:
        data = await self.repository.dashboard_data()
        metrics = data.pop("turn_metrics")
        assert isinstance(metrics, list)
        grouped: dict[str | None, dict[str, int]] = {}
        grounded_turns = 0
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        turns_without_token_usage = 0
        for metric in metrics:
            assert isinstance(metric, DiagnosisTurnMetrics)
            group = grouped.setdefault(
                metric.model,
                {
                    "turns": 0,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "turns_without_token_usage": 0,
                },
            )
            group["turns"] += 1
            if metric.chunks_used_count > 0:
                grounded_turns += 1
            if metric.input_tokens is None or metric.output_tokens is None:
                turns_without_token_usage += 1
                group["turns_without_token_usage"] += 1
            else:
                input_tokens += metric.input_tokens
                cached_input_tokens += metric.cached_input_tokens or 0
                output_tokens += metric.output_tokens
                group["input_tokens"] += metric.input_tokens
                group["cached_input_tokens"] += metric.cached_input_tokens or 0
                group["output_tokens"] += metric.output_tokens
        return MindDashboardOverviewRead(
            diagnosis_sessions=cast(int, data["diagnosis_sessions"]),
            sessions_in_progress=cast(int, data["sessions_in_progress"]),
            submitted_requests=cast(int, data["submitted_requests"]),
            possibly_ungrounded_requests=cast(int, data["possibly_ungrounded_requests"]),
            assistant_turns=len(metrics),
            grounded_turns=grounded_turns,
            turns_without_token_usage=turns_without_token_usage,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            knowledge_sources=cast(int, data["knowledge_sources"]),
            knowledge_chunks=cast(int, data["knowledge_chunks"]),
            last_knowledge_update_at=data["last_knowledge_update_at"],
            model_usage=[
                DiagnosisModelUsageRead(model=model, **values)
                for model, values in sorted(grouped.items(), key=lambda item: item[0] or "")
            ],
        )

    async def _build_turn_context(
        self, *, session_id: uuid.UUID, content: str
    ) -> tuple[str, list[LLMMessage], list[tuple[KnowledgeChunk, float]], DiagnosisGovernanceRead]:
        """Persists the visitor's message, then assembles what this turn's LLM
        call needs: a grounded system prompt (§2.2a), a fixed-size window of
        recent messages instead of the full transcript (§2.3), and the
        retrieved chunks (for the turn metrics recorded by the caller).
        Raises ValidationDomainError once diagnosis_max_turns is reached,
        before persisting the message or calling the LLM.
        """
        governance = await self.get_governance()
        turns_used = await self.repository.count_user_messages(session_id)
        if turns_used >= governance.diagnosis_max_turns:
            raise ValidationDomainError(
                f"This diagnosis session reached its {governance.diagnosis_max_turns}-turn "
                "limit -- submit what has been gathered so far instead of continuing."
            )

        await self.repository.add_message(
            diagnosis_session_id=session_id, role="user", content=content
        )

        retrieved = await self.knowledge_service.search(
            query=content,
            top_k=governance.diagnosis_grounding_top_k,
            min_score=governance.diagnosis_grounding_min_score,
        )
        chunks = [chunk for chunk, _score in retrieved]
        system_prompt = _build_grounded_system_prompt(chunks)

        history = await self.repository.list_recent_messages(
            session_id, limit=governance.diagnosis_max_history_messages
        )
        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]
        return system_prompt, llm_messages, retrieved, governance

    async def _record_turn_metrics(
        self,
        *,
        session_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        retrieved: list[tuple[KnowledgeChunk, float]],
        input_tokens: int | None,
        cached_input_tokens: int | None,
        output_tokens: int | None,
        model: str | None,
    ) -> None:
        # "Used" here means "retrieved and injected into the prompt for this
        # turn" -- a proxy for what the model had available, not a verified
        # citation count (there's no reliable way to confirm the model
        # actually quoted a given chunk without fragile text-matching).
        chunks_retrieved = [
            {"chunk_id": str(chunk.id), "score": round(score, 4)} for chunk, score in retrieved
        ]
        await self.repository.add_turn_metrics(
            diagnosis_session_id=session_id,
            assistant_message_id=assistant_message_id,
            chunks_retrieved=chunks_retrieved,
            chunks_used_count=len(retrieved),
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            model=model,
        )

    @staticmethod
    def _preview(
        extraction: DiagnosisExtraction, *, grounded: bool
    ) -> DiagnosisPreview:
        missing_information: list[str] = []
        if not extraction.problem_summary.strip():
            missing_information.append("descrever o problema ou objetivo")
        if not extraction.services_of_interest:
            missing_information.append("identificar ao menos um serviço de interesse")
        if not extraction.contact_name:
            missing_information.append("nome")
        if not extraction.contact_email:
            missing_information.append("e-mail")

        return DiagnosisPreview(
            problem_summary=extraction.problem_summary,
            services_of_interest=extraction.services_of_interest,
            budget_range=extraction.budget_range,
            timeline=extraction.timeline,
            missing_information=missing_information,
            grounding_status="grounded" if grounded else "unavailable",
        )

    async def send_message(
        self, *, session_id: uuid.UUID, content: str
    ) -> tuple[DiagnosisMessage, bool, DiagnosisPreview]:
        await self.repository.get_session(session_id)
        system_prompt, llm_messages, retrieved, governance = await self._build_turn_context(
            session_id=session_id, content=content
        )

        response = await self._complete_reply(
            system=system_prompt,
            messages=llm_messages,
            max_tokens=governance.diagnosis_max_output_tokens,
        )
        assistant_message = await self.repository.add_message(
            diagnosis_session_id=session_id, role="assistant", content=response.content
        )
        await self._record_turn_metrics(
            session_id=session_id,
            assistant_message_id=assistant_message.id,
            retrieved=retrieved,
            input_tokens=response.usage.input_tokens,
            cached_input_tokens=response.usage.cached_input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

        extraction = await self._extract(
            llm_messages + [LLMMessage(role="assistant", content=response.content)],
            max_tokens=governance.diagnosis_max_output_tokens,
        )
        preview = self._preview(extraction, grounded=bool(retrieved))
        ready_to_submit = extraction.ready_to_submit and not preview.missing_information
        return assistant_message, ready_to_submit, preview

    async def _complete_reply(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        await self.llm_usage_service.ensure_budget(
            flow="diagnosis_chat",
            model=settings.maritaca_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        response = await self.llm_provider.complete(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        await self.llm_usage_service.record(
            flow="diagnosis_chat", operation="reply", response=response
        )
        return response

    async def stream_message(
        self, *, session_id: uuid.UUID, content: str
    ) -> AsyncIterator[dict[str, object]]:
        """Yields SSE-ready event dicts: {"type": "delta", "content": ...} per chunk,
        then a final {"type": "done", "ready_to_submit": ..., "message_id": ...}.
        Yields {"type": "error", "detail": ...} instead of raising when the turn
        cap is hit -- by the time this generator runs, the HTTP response has
        already started with a 200 status, so a raised exception can't turn
        into a proper error status code the way it does in send_message.
        """
        await self.repository.get_session(session_id)
        try:
            system_prompt, llm_messages, retrieved, governance = await self._build_turn_context(
                session_id=session_id, content=content
            )
        except ValidationDomainError as exc:
            yield {"type": "error", "detail": exc.detail}
            return

        full_content = ""
        try:
            await self.llm_usage_service.ensure_budget(
                flow="diagnosis_chat",
                model=settings.maritaca_model,
                system=system_prompt,
                messages=llm_messages,
                max_tokens=governance.diagnosis_max_output_tokens,
            )
        except (LLMBudgetExceededError, LLMPricingUnavailableError) as exc:
            yield {"type": "error", "detail": exc.detail}
            return
        stream_response: LLMResponse | None = None
        async for event in self.llm_provider.complete_stream(
            system=system_prompt,
            messages=llm_messages,
            max_tokens=governance.diagnosis_max_output_tokens,
        ):
            if event.type == "delta":
                full_content += event.content
                yield {"type": "delta", "content": event.content}
            elif event.response is not None:
                stream_response = event.response

        assistant_message = await self.repository.add_message(
            diagnosis_session_id=session_id, role="assistant", content=full_content
        )
        # The external SSE contract stays delta/done, while the provider's
        # final ``response.completed`` event supplies exact token usage.
        await self._record_turn_metrics(
            session_id=session_id,
            assistant_message_id=assistant_message.id,
            retrieved=retrieved,
            input_tokens=stream_response.usage.input_tokens if stream_response else None,
            cached_input_tokens=(
                stream_response.usage.cached_input_tokens if stream_response else None
            ),
            output_tokens=stream_response.usage.output_tokens if stream_response else None,
            model=stream_response.model if stream_response else None,
        )
        if stream_response is not None:
            await self.llm_usage_service.record(
                flow="diagnosis_chat", operation="reply_stream", response=stream_response
            )
        extraction = await self._extract(
            llm_messages + [LLMMessage(role="assistant", content=full_content)],
            max_tokens=governance.diagnosis_max_output_tokens,
        )
        preview = self._preview(extraction, grounded=bool(retrieved))
        ready_to_submit = extraction.ready_to_submit and not preview.missing_information
        yield {
            "type": "done",
            "ready_to_submit": ready_to_submit,
            "message_id": str(assistant_message.id),
            "preview": preview.model_dump(),
        }

    async def _extract(self, messages: list[LLMMessage], *, max_tokens: int) -> DiagnosisExtraction:
        await self.llm_usage_service.ensure_budget(
            flow="diagnosis_extraction",
            model=settings.maritaca_model,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=max_tokens,
            schema_text=json.dumps(DiagnosisExtraction.model_json_schema(), sort_keys=True),
        )
        result = await self.llm_provider.complete_structured(
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=messages,
            schema=DiagnosisExtraction,
            max_tokens=max_tokens,
        )
        await self.llm_usage_service.record(
            flow="diagnosis_extraction", operation="extract", response=result.response
        )
        assert isinstance(result.data, DiagnosisExtraction)
        return result.data

    async def submit(self, *, session_id: uuid.UUID) -> DiagnosisRequest:
        """Contact details (name/email/phone/company/cnpj) come from the
        conversation's own extraction, not as call arguments -- the LLM
        gathers them naturally during the chat (see DIAGNOSIS_SYSTEM_PROMPT),
        so the caller never needs a separate signup form for them.

        Uses the FULL transcript (not the fixed per-turn window) -- this is a
        one-time call at the end of the session, not a per-turn cost driver,
        and the final extraction/record benefits from seeing everything.
        """
        diagnosis_session = await self.repository.get_session(session_id)
        history = await self.repository.list_messages(session_id)
        if not history:
            raise ValidationDomainError("Cannot submit a diagnosis request with no conversation")

        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]
        governance = await self.get_governance()
        extraction = await self._extract(
            llm_messages, max_tokens=governance.diagnosis_max_output_tokens
        )
        turn_metrics = await self.repository.list_turn_metrics(session_id)
        preview = self._preview(
            extraction, grounded=any(tm.chunks_used_count > 0 for tm in turn_metrics)
        )
        if not extraction.ready_to_submit or preview.missing_information:
            raise ValidationDomainError(
                "Not enough information has been gathered yet to submit a diagnosis request"
            )

        possibly_ungrounded = not any(tm.chunks_used_count > 0 for tm in turn_metrics)

        diagnosis_request = await self.repository.create_request(
            diagnosis_session_id=diagnosis_session.id,
            contact_name=extraction.contact_name,
            contact_email=extraction.contact_email,
            contact_phone=extraction.contact_phone,
            company_name=extraction.company_name,
            cnpj=extraction.cnpj,
            problem_summary=extraction.problem_summary,
            services_of_interest=extraction.services_of_interest,
            budget_range=extraction.budget_range,
            timeline=extraction.timeline,
            raw_transcript_snapshot=[{"role": m.role, "content": m.content} for m in history],
            possibly_ungrounded=possibly_ungrounded,
        )
        await self.repository.mark_completed(diagnosis_session)
        return diagnosis_request

    async def list_requests(self) -> list[DiagnosisRequest]:
        return await self.repository.list_requests()
