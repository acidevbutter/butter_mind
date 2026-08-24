import uuid
from collections.abc import AsyncIterator

from app.core.decorators import log_errors
from app.core.exceptions import ValidationDomainError
from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import LLMMessage
from app.diagnosis.models import (
    DiagnosisMessage,
    DiagnosisRequest,
    DiagnosisSession,
    DiagnosisTurnMetrics,
)
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.schemas import DiagnosisExtraction, DiagnosisPreview, DiagnosisSessionCreate
from app.knowledge.models import KnowledgeChunk
from app.knowledge.service import KnowledgeIngestionService
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
    ):
        self.repository = repository
        self.llm_provider = llm_provider
        self.knowledge_service = knowledge_service

    async def create_session(self, payload: DiagnosisSessionCreate) -> DiagnosisSession:
        return await self.repository.create_session(payload)

    async def get_session(self, session_id: uuid.UUID) -> DiagnosisSession:
        return await self.repository.get_session(session_id)

    async def list_messages(self, session_id: uuid.UUID) -> list[DiagnosisMessage]:
        return await self.repository.list_messages(session_id)

    async def list_turn_metrics(self, session_id: uuid.UUID) -> list[DiagnosisTurnMetrics]:
        return await self.repository.list_turn_metrics(session_id)

    async def _build_turn_context(
        self, *, session_id: uuid.UUID, content: str
    ) -> tuple[str, list[LLMMessage], list[tuple[KnowledgeChunk, float]]]:
        """Persists the visitor's message, then assembles what this turn's LLM
        call needs: a grounded system prompt (§2.2a), a fixed-size window of
        recent messages instead of the full transcript (§2.3), and the
        retrieved chunks (for the turn metrics recorded by the caller).
        Raises ValidationDomainError once diagnosis_max_turns is reached,
        before persisting the message or calling the LLM.
        """
        turns_used = await self.repository.count_user_messages(session_id)
        if turns_used >= settings.diagnosis_max_turns:
            raise ValidationDomainError(
                f"This diagnosis session reached its {settings.diagnosis_max_turns}-turn "
                "limit -- submit what has been gathered so far instead of continuing."
            )

        await self.repository.add_message(
            diagnosis_session_id=session_id, role="user", content=content
        )

        retrieved = await self.knowledge_service.search(
            query=content,
            top_k=settings.diagnosis_grounding_top_k,
            min_score=settings.diagnosis_grounding_min_score,
        )
        chunks = [chunk for chunk, _score in retrieved]
        system_prompt = _build_grounded_system_prompt(chunks)

        history = await self.repository.list_recent_messages(
            session_id, limit=settings.diagnosis_max_history_messages
        )
        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]
        return system_prompt, llm_messages, retrieved

    async def _record_turn_metrics(
        self,
        *,
        session_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        retrieved: list[tuple[KnowledgeChunk, float]],
        input_tokens: int | None,
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
        system_prompt, llm_messages, retrieved = await self._build_turn_context(
            session_id=session_id, content=content
        )

        response = await self.llm_provider.complete(
            system=system_prompt,
            messages=llm_messages,
            max_tokens=settings.diagnosis_max_output_tokens,
        )
        assistant_message = await self.repository.add_message(
            diagnosis_session_id=session_id, role="assistant", content=response.content
        )
        await self._record_turn_metrics(
            session_id=session_id,
            assistant_message_id=assistant_message.id,
            retrieved=retrieved,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

        extraction = await self._extract(
            llm_messages + [LLMMessage(role="assistant", content=response.content)]
        )
        preview = self._preview(extraction, grounded=bool(retrieved))
        ready_to_submit = extraction.ready_to_submit and not preview.missing_information
        return assistant_message, ready_to_submit, preview

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
            system_prompt, llm_messages, retrieved = await self._build_turn_context(
                session_id=session_id, content=content
            )
        except ValidationDomainError as exc:
            yield {"type": "error", "detail": exc.detail}
            return

        full_content = ""
        async for delta in self.llm_provider.complete_stream(
            system=system_prompt,
            messages=llm_messages,
            max_tokens=settings.diagnosis_max_output_tokens,
        ):
            full_content += delta
            yield {"type": "delta", "content": delta}

        assistant_message = await self.repository.add_message(
            diagnosis_session_id=session_id, role="assistant", content=full_content
        )
        # complete_stream yields plain text deltas (AsyncIterator[str]) -- it
        # doesn't expose usage today, and devbutter_backend's Socket.IO relay
        # (docs/plano-streaming-socketio-chat.md) already consumes it under
        # that contract, so token counts for streamed turns are recorded as
        # unknown (None) rather than changing that interface here. TODO:
        # thread `stream_options={"include_usage": True}` through a richer
        # return type if per-streamed-turn token accounting becomes necessary.
        await self._record_turn_metrics(
            session_id=session_id,
            assistant_message_id=assistant_message.id,
            retrieved=retrieved,
            input_tokens=None,
            output_tokens=None,
            model=None,
        )
        extraction = await self._extract(
            llm_messages + [LLMMessage(role="assistant", content=full_content)]
        )
        preview = self._preview(extraction, grounded=bool(retrieved))
        ready_to_submit = extraction.ready_to_submit and not preview.missing_information
        yield {
            "type": "done",
            "ready_to_submit": ready_to_submit,
            "message_id": str(assistant_message.id),
            "preview": preview.model_dump(),
        }

    async def _extract(self, messages: list[LLMMessage]) -> DiagnosisExtraction:
        result = await self.llm_provider.complete_structured(
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=messages,
            schema=DiagnosisExtraction,
            max_tokens=settings.diagnosis_max_output_tokens,
        )
        assert isinstance(result, DiagnosisExtraction)
        return result

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
        extraction = await self._extract(llm_messages)
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
