import uuid

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
    "Seja cordial, faça uma pergunta de cada vez, e não invente informações que o visitante não deu."
)

EXTRACTION_SYSTEM_PROMPT = (
    "Analise a conversa entre um visitante e o assistente de diagnóstico da DevButter. "
    "Extraia os campos estruturados pedidos. Marque ready_to_submit=true somente se já houver "
    "informação suficiente para descrever o problema do visitante e ao menos um serviço de interesse; "
    "caso contrário, ready_to_submit=false."
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

    async def _extract(self, messages: list[LLMMessage]) -> DiagnosisExtraction:
        result = await self.llm_provider.complete_structured(
            system=EXTRACTION_SYSTEM_PROMPT, messages=messages, schema=DiagnosisExtraction,
        )
        assert isinstance(result, DiagnosisExtraction)
        return result

    async def submit(
        self,
        *,
        session_id: uuid.UUID,
        contact_name: str | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        company_name: str | None = None,
    ) -> DiagnosisRequest:
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
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            company_name=company_name,
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
