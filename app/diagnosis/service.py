import uuid
from collections.abc import AsyncIterator

from app.core.decorators import log_errors
from app.core.exceptions import ValidationDomainError
from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import LLMMessage
from app.diagnosis.models import DiagnosisMessage, DiagnosisRequest, DiagnosisSession
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.schemas import DiagnosisExtraction, DiagnosisSessionCreate

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
    "Seja cordial, faça uma pergunta de cada vez, e não invente informações que o visitante não deu."
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


@log_errors
class DiagnosisService:
    def __init__(self, repository: DiagnosisRepository, llm_provider: LLMProvider):
        self.repository = repository
        self.llm_provider = llm_provider

    async def create_session(self, payload: DiagnosisSessionCreate) -> DiagnosisSession:
        return await self.repository.create_session(payload)

    async def get_session(self, session_id: uuid.UUID) -> DiagnosisSession:
        return await self.repository.get_session(session_id)

    async def list_messages(self, session_id: uuid.UUID) -> list[DiagnosisMessage]:
        return await self.repository.list_messages(session_id)

    async def send_message(self, *, session_id: uuid.UUID, content: str) -> tuple[DiagnosisMessage, bool]:
        await self.repository.get_session(session_id)
        await self.repository.add_message(diagnosis_session_id=session_id, role="user", content=content)

        history = await self.repository.list_messages(session_id)
        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]

        response = await self.llm_provider.complete(system=DIAGNOSIS_SYSTEM_PROMPT, messages=llm_messages)
        assistant_message = await self.repository.add_message(
            diagnosis_session_id=session_id, role="assistant", content=response.content
        )

        extraction = await self._extract(llm_messages + [LLMMessage(role="assistant", content=response.content)])
        return assistant_message, extraction.ready_to_submit

    async def stream_message(self, *, session_id: uuid.UUID, content: str) -> AsyncIterator[dict]:
        """Yields SSE-ready event dicts: {"type": "delta", "content": ...} per chunk,
        then a final {"type": "done", "ready_to_submit": ..., "message_id": ...}.
        """
        await self.repository.get_session(session_id)
        await self.repository.add_message(diagnosis_session_id=session_id, role="user", content=content)

        history = await self.repository.list_messages(session_id)
        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]

        full_content = ""
        async for delta in self.llm_provider.complete_stream(system=DIAGNOSIS_SYSTEM_PROMPT, messages=llm_messages):
            full_content += delta
            yield {"type": "delta", "content": delta}

        assistant_message = await self.repository.add_message(
            diagnosis_session_id=session_id, role="assistant", content=full_content
        )
        extraction = await self._extract(llm_messages + [LLMMessage(role="assistant", content=full_content)])
        yield {
            "type": "done",
            "ready_to_submit": extraction.ready_to_submit,
            "message_id": str(assistant_message.id),
        }

    async def _extract(self, messages: list[LLMMessage]) -> DiagnosisExtraction:
        result = await self.llm_provider.complete_structured(
            system=EXTRACTION_SYSTEM_PROMPT, messages=messages, schema=DiagnosisExtraction,
        )
        assert isinstance(result, DiagnosisExtraction)
        return result

    async def submit(self, *, session_id: uuid.UUID) -> DiagnosisRequest:
        """Contact details (name/email/phone/company/cnpj) come from the
        conversation's own extraction, not as call arguments -- the LLM
        gathers them naturally during the chat (see DIAGNOSIS_SYSTEM_PROMPT),
        so the caller never needs a separate signup form for them.
        """
        diagnosis_session = await self.repository.get_session(session_id)
        history = await self.repository.list_messages(session_id)
        if not history:
            raise ValidationDomainError("Cannot submit a diagnosis request with no conversation")

        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]
        extraction = await self._extract(llm_messages)
        if not extraction.ready_to_submit:
            raise ValidationDomainError(
                "Not enough information has been gathered yet to submit a diagnosis request"
            )

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
        )
        await self.repository.mark_completed(diagnosis_session)
        return diagnosis_request

    async def list_requests(self) -> list[DiagnosisRequest]:
        return await self.repository.list_requests()
