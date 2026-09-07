import json
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator
from typing import cast

from app.core.decorators import log_errors
from app.core.exceptions import ConflictError, ValidationDomainError
from app.core.llm.exceptions import LLMBudgetExceededError, LLMPricingUnavailableError
from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import LLMMessage, LLMResponse
from app.core.metrics import emit_metrics
from app.diagnosis.models import (
    DiagnosisMessage,
    DiagnosisRequest,
    DiagnosisSession,
    DiagnosisTurnMetrics,
)
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.schemas import (
    REQUIRED_PROFILE_FIELDS,
    BusinessMetric,
    BusinessProfile,
    BusinessProfilePatch,
    DiagnosisExtraction,
    DiagnosisGovernanceRead,
    DiagnosisGovernanceUpdate,
    DiagnosisModelUsageRead,
    DiagnosisPreview,
    DiagnosisSessionCreate,
    DiagnosisStage,
    DiagnosisSubmitRequest,
    MindDashboardOverviewRead,
    NextStep,
    NextStepField,
    NextStepOption,
    ProductOption,
    ProductOptionDraft,
    QualificationProgress,
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
    "não deu. Quando entender o problema e o porte do negócio (volume, canal, equipe), apresente "
    "de 2 a 3 caminhos possíveis, cada um com uma faixa de investimento e de prazo em texto "
    "(nunca valor fechado), e deixe claro que são estimativas sujeitas à revisão do Marcos. "
    "Depois que o visitante escolher um caminho, confirme com ele os dados do negócio que "
    "faltarem (nome da empresa, segmento, quem é o contato), aceitando 'pular por agora'."
)

GROUNDING_INSTRUCTION = (
    "Use as informações reais abaixo, extraídas da base de conhecimento da DevButter, como "
    "fonte de verdade para preços, prazos e serviços. Se a pergunta do visitante não for "
    "coberta por elas, diga com honestidade que você não tem essa informação específica em "
    "vez de inventar um valor ou prazo."
)

# Bump when the extraction prompt or _OPTION_CATALOG changes -- lets an admin
# view correlate extraction quality with a prompt revision (see
# devbutter_app/docs/architecture/ai-quote-recommended-flow.md, "Métricas
# mínimas por etapa": prompt_version).
EXTRACTION_PROMPT_VERSION = "2026-09-02-product-options"

EXTRACTION_SYSTEM_PROMPT = (
    "Analise a conversa entre um visitante e o assistente de diagnóstico da DevButter. "
    "Extraia os campos estruturados pedidos: resumo do problema, serviços de interesse, faixa de "
    "orçamento, prazo, e os dados de contato que o visitante tiver compartilhado (contact_name, "
    "contact_email, contact_phone, company_name, cnpj) -- extraia-os exatamente como o visitante "
    "escreveu, sem inventar ou completar dados que não foram ditos. Marque ready_to_submit=true "
    "somente se já houver informação suficiente para descrever o problema do visitante, ao menos "
    "um serviço de interesse, E contact_name e contact_email; caso qualquer um desses falte, "
    "ready_to_submit=false. "
    "Enquanto ready_to_submit=false, escolha em next_step_field qual informação faz mais sentido "
    "coletar no próximo passo, oferecendo opções para o visitante tocar: 'business_type' (que "
    "tipo de negócio), 'problem_area' (que área o problema afeta), 'services_of_interest' (que "
    "serviço a DevButter faria), 'budget_range' (faixa de investimento) ou 'timeline' (prazo). "
    "Prefira a informação que ainda está vazia ou vaga. Em next_step_prompt escreva uma pergunta "
    "curta em português (até ~90 caracteres) para aparecer acima das opções. Se a conversa não "
    "comporta opções fechadas agora, use next_step_field='none'. Quando ready_to_submit=true, "
    "sempre use next_step_field='none'. Não invente rótulos de opção -- só escolha o campo. "
    "Preencha também o perfil do negócio conforme a conversa revela, sem inventar: "
    "is_legal_entity=true se o visitante fala em nome de uma empresa/CNPJ, false se é para uso "
    "pessoal, null se ainda não deu para saber; business_segment (ex.: 'moda / varejo', "
    "'saúde', 'educação'); daily_volume como texto curto do volume citado (ex.: '~150 "
    "conversas/dia', '2 mil pedidos/mês'); pain_points com as dores concretas mencionadas; "
    "scope_modules com os blocos de solução que já estão claros (ex.: 'Agente treinado no "
    "catálogo', 'Consulta de frete', 'Checkout no WhatsApp'). Deixe vazio o que não foi dito. "
    "Preencha city com a cidade/UF do negócio se ela aparecer na conversa (ex.: 'Curitiba PR'). "
    "Em business_metrics liste de 0 a 4 números curtos que o visitante citou sobre o negócio, "
    "cada um com label (ex.: 'conversas / dia', 'atendentes'), value como texto curto (ex.: "
    "'~150', '2', '~4h') e computed=false. Use computed=true apenas para uma figura que você "
    "mesmo calculou a partir do que foi dito (ex.: horas por dia gastas repetindo respostas); "
    "nunca crie um business_metric para um número que não foi mencionado. "
    "Quando já houver problema claro + porte/canal (volume, equipe ou similar), preencha "
    "proposed_options com 2 ou 3 caminhos possíveis para resolver, cada um com title curto, "
    "summary de 1-2 frases, price_range e timeline SEMPRE como faixa em texto ('R$ 8k–15k', "
    "'6–8 semanas') e nunca valor fechado, e recommended=true no mais indicado (apenas um). "
    "Baseie os caminhos e as faixas nas informações reais da base de conhecimento; se não "
    "houver base para uma faixa, deixe price_range=null. Se ainda não dá para propor caminhos, "
    "deixe proposed_options vazio."
)

# Fixed option catalog. The LLM only picks WHICH field to ask next
# (next_step_field); the option ids/labels below are the single source of truth,
# so the browser and the persisted transcript never see a drifting label. Order
# here is the render order. pt-BR labels, <= 32 chars.
_OPTION_CATALOG: dict[str, list[tuple[str, str]]] = {
    "business_type": [
        ("biz_ecommerce", "Loja / e-commerce"),
        ("biz_saas", "SaaS / plataforma"),
        ("biz_services", "Prestação de serviços"),
        ("biz_industry", "Indústria / varejo"),
        ("biz_startup", "Startup em validação"),
        ("biz_other", "Outro"),
    ],
    "problem_area": [
        ("prob_support", "Atendimento / suporte"),
        ("prob_sales", "Vendas / geração de leads"),
        ("prob_ops", "Operação / processos internos"),
        ("prob_data", "Dados / relatórios"),
        ("prob_product", "Produto digital novo"),
        ("prob_integration", "Integração entre sistemas"),
    ],
    "services_of_interest": [
        ("svc_ai_agent", "Agente de IA"),
        ("svc_automation", "Automação de processos"),
        ("svc_platform", "Plataforma web / SaaS"),
        ("svc_ecommerce", "E-commerce"),
        ("svc_website", "Site institucional"),
        ("svc_data", "Dados / analytics"),
    ],
    "budget_range": [
        ("budget_lt_10k", "Até R$ 10 mil"),
        ("budget_10_30k", "R$ 10–30 mil"),
        ("budget_30_80k", "R$ 30–80 mil"),
        ("budget_gt_80k", "Acima de R$ 80 mil"),
        ("budget_unsure", "Ainda não sei"),
    ],
    "timeline": [
        ("time_asap", "O quanto antes"),
        ("time_1_3m", "1–3 meses"),
        ("time_3_6m", "3–6 meses"),
        ("time_flexible", "Sem prazo fixo"),
    ],
}

_DEFAULT_NEXT_STEP_PROMPT: dict[str, str] = {
    "business_type": "Que tipo de negócio é o seu?",
    "problem_area": "Onde esse problema mais pesa hoje?",
    "services_of_interest": "Que tipo de solução você imagina? (pode marcar mais de uma)",
    "budget_range": "Tem uma faixa de investimento em mente?",
    "timeline": "Qual o prazo que você tem em mente?",
}

_MAX_NEXT_STEP_PROMPT_CHARS = 160


def _build_next_step(field: str, prompt: str | None) -> NextStep | None:
    """Expand the LLM's chosen field into a full NextStep from _OPTION_CATALOG.
    Returns None for 'none', an unknown field, or a catalog entry with < 2
    options -- callers then just render the composer."""
    options = _OPTION_CATALOG.get(field)
    if not options or len(options) < 2:
        return None
    text = (prompt or "").strip() or _DEFAULT_NEXT_STEP_PROMPT[field]
    return NextStep(
        prompt=text[:_MAX_NEXT_STEP_PROMPT_CHARS],
        field=cast(NextStepField, field),
        selection_mode="multi" if field == "services_of_interest" else "single",
        allow_free_text=True,
        options=[NextStepOption(id=oid, label=label) for oid, label in options],
    )


# ---- ADR-0004: product options + business profile + stage --------------------

_MAX_OPTION_TITLE_CHARS = 80
_MAX_OPTION_SUMMARY_CHARS = 280


def _slugify(text: str) -> str:
    """Stable snake_case key from an option title -- the LLM never supplies the
    key, so it stays put even as the model rephrases the title across turns."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return f"opt_{slug[:40] or 'path'}"


def _sanitize_options(drafts: list[ProductOptionDraft]) -> list[ProductOption]:
    """0 options (still qualifying) or 2-3 keyed, deduped, exactly-one-
    recommended ProductOptions. A single draft is dropped -- never render a
    one-option chooser."""
    seen: set[str] = set()
    out: list[ProductOption] = []
    recommended_index: int | None = None
    for draft in drafts:
        title = (draft.title or "").strip()
        if not title:
            continue
        key = _slugify(title)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            ProductOption(
                key=key,
                title=title[:_MAX_OPTION_TITLE_CHARS],
                summary=(draft.summary or "").strip()[:_MAX_OPTION_SUMMARY_CHARS],
                price_range=(draft.price_range or None),
                timeline=(draft.timeline or None),
                recommended=False,
            )
        )
        if draft.recommended and recommended_index is None:
            recommended_index = len(out) - 1
        if len(out) == 3:
            break
    if len(out) < 2:
        return []
    # Exactly one recommended, aligned with the drafts that actually landed
    # in `out` (empty titles / duplicate keys are skipped above).
    rec_index = recommended_index if recommended_index is not None else 0
    for i, opt in enumerate(out):
        opt.recommended = i == rec_index
    return out


def _extraction_profile(extraction: DiagnosisExtraction) -> dict[str, object]:
    """The business-profile fields butter_mind can infer from the transcript
    this turn (recomputed every turn -- stateless)."""
    return {
        "business_name": extraction.company_name,
        "segment": extraction.business_segment,
        "city": extraction.city,
        "volume": extraction.daily_volume,
        "contact_name": extraction.contact_name,
        "contact_email": extraction.contact_email,
        "contact_phone": extraction.contact_phone,
    }


def _effective_profile(
    extraction: DiagnosisExtraction, session_profile: dict[str, object]
) -> dict[str, object]:
    """Session-collected fields (from PATCH /business-profile) win over the
    per-turn extraction for the same key."""
    merged = _extraction_profile(extraction)
    for key, value in (session_profile or {}).items():
        merged[key] = value
    return merged


def _missing_profile_fields(profile: dict[str, object]) -> list[str]:
    return [f for f in REQUIRED_PROFILE_FIELDS if not (profile.get(f) or "")]


def _lead_scope_complete(extraction: DiagnosisExtraction) -> bool:
    """Problem + at least one service -- the extraction prompt's bar for a
    submitable lead, independent of the LLM's own ready_to_submit flag."""
    return bool(extraction.problem_summary.strip()) and bool(extraction.services_of_interest)


def _compute_stage(
    *,
    selected_option_key: str | None,
    options: list[ProductOption],
    missing_fields: list[str],
    lead_scope_complete: bool,
) -> DiagnosisStage:
    if selected_option_key and not missing_fields and lead_scope_complete:
        return "ready"
    if selected_option_key:
        return "collecting"
    if len(options) >= 2:
        return "choosing"
    return "qualifying"


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
            rag_enabled=settings.rag_enabled,
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
        average_score = (
            sum(score for _chunk, score in retrieved) / len(retrieved) if retrieved else 0
        )
        await emit_metrics(
            dimensions={"Flow": "diagnosis_chat"},
            values={
                "DiagnosisChunksUsed": (len(retrieved), "Count"),
                "DiagnosisGroundingScore": (average_score, "None"),
            },
        )

    @staticmethod
    def _preview(
        extraction: DiagnosisExtraction,
        *,
        grounded: bool,
        session: DiagnosisSession | None = None,
    ) -> DiagnosisPreview:
        session_profile = dict(session.business_profile) if session else {}
        selected_key = session.selected_option_key if session else None
        options_snapshot = list(session.options_snapshot) if session else []

        effective_profile = _effective_profile(extraction, session_profile)
        missing_fields = _missing_profile_fields(effective_profile)

        if selected_key:
            chosen = next((o for o in options_snapshot if o.get("key") == selected_key), None)
            options = [ProductOption(**chosen)] if chosen else []
        else:
            options = _sanitize_options(extraction.proposed_options)
        stage = _compute_stage(
            selected_option_key=selected_key,
            options=options,
            missing_fields=missing_fields,
            lead_scope_complete=_lead_scope_complete(extraction),
        )

        missing_information: list[str] = []
        if not extraction.problem_summary.strip():
            missing_information.append("descrever o problema ou objetivo")
        if not extraction.services_of_interest:
            missing_information.append("identificar ao menos um serviço de interesse")
        if not (effective_profile.get("contact_name") or ""):
            missing_information.append("nome")
        if not (effective_profile.get("contact_email") or ""):
            missing_information.append("e-mail")

        # `next_step` (canvas 1c pills) only makes sense while still qualifying;
        # once the concierge is proposing paths, the option cards take over.
        next_step = (
            _build_next_step(extraction.next_step_field, extraction.next_step_prompt)
            if stage == "qualifying"
            else None
        )

        # Fixed qualification checklist behind the "X de N perguntas" counter
        # (canvas screen 1c). Order mirrors how the concierge naturally walks
        # the conversation: problem -> who they are -> scale -> scope -> money.
        checkpoints = [
            bool(extraction.problem_summary.strip()),
            extraction.is_legal_entity is not None
            or bool(extraction.business_segment)
            or bool(extraction.company_name),
            bool(extraction.daily_volume)
            or bool(extraction.pain_points)
            or bool(extraction.business_metrics),
            bool(extraction.services_of_interest) or bool(extraction.scope_modules),
            bool(extraction.budget_range) or bool(extraction.timeline),
        ]
        metrics = list(extraction.business_metrics)
        session_metrics = session_profile.get("metrics")
        if isinstance(session_metrics, list) and session_metrics and not metrics:
            metrics = [BusinessMetric(**m) for m in session_metrics]
        business_profile = BusinessProfile(
            company_name=cast(str | None, effective_profile.get("business_name")),
            is_legal_entity=extraction.is_legal_entity,
            segment=cast(str | None, effective_profile.get("segment")),
            city=cast(str | None, effective_profile.get("city")),
            volume=cast(str | None, effective_profile.get("volume")),
            metrics=metrics,
            pain_points=extraction.pain_points,
            scope_modules=extraction.scope_modules or extraction.services_of_interest,
            contact_ready=bool(
                effective_profile.get("contact_name") and effective_profile.get("contact_email")
            ),
        )

        return DiagnosisPreview(
            problem_summary=extraction.problem_summary,
            services_of_interest=extraction.services_of_interest,
            budget_range=(
                options[0].price_range if selected_key and options else extraction.budget_range
            ),
            timeline=(options[0].timeline if selected_key and options else extraction.timeline),
            missing_information=missing_information,
            grounding_status="grounded" if grounded else "unavailable",
            next_step=next_step,
            business_profile=business_profile,
            progress=QualificationProgress(answered=sum(checkpoints), total=len(checkpoints)),
            stage=stage,
            options=options,
            selected_option_key=selected_key,
            missing_fields=missing_fields,
        )

    async def send_message(
        self, *, session_id: uuid.UUID, content: str
    ) -> tuple[DiagnosisMessage, bool, DiagnosisPreview]:
        session = await self.repository.get_session(session_id)
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
        preview = self._preview(extraction, grounded=bool(retrieved), session=session)
        await self._persist_turn_state(session, preview)
        return assistant_message, preview.stage == "ready", preview

    async def _persist_turn_state(
        self, session: DiagnosisSession, preview: DiagnosisPreview
    ) -> None:
        """Carry the computed stage forward, and snapshot the proposed options
        while the visitor is choosing so select-option can validate the key.
        Drop the snapshot (and any leftover selection) when the concierge
        falls back to qualifying -- otherwise a stale key still validates."""
        updates: dict[str, object] = {"stage": preview.stage}
        if preview.stage == "choosing" and preview.options:
            updates["options_snapshot"] = [o.model_dump() for o in preview.options]
        elif preview.stage == "qualifying":
            updates["options_snapshot"] = []
            updates["selected_option_key"] = None
        await self.repository.update_session(session, **updates)

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
        session = await self.repository.get_session(session_id)
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
        preview = self._preview(extraction, grounded=bool(retrieved), session=session)
        await self._persist_turn_state(session, preview)
        yield {
            "type": "done",
            "ready_to_submit": preview.stage == "ready",
            "message_id": str(assistant_message.id),
            "preview": preview.model_dump(),
        }

    async def _recompute_preview(
        self, session: DiagnosisSession
    ) -> tuple[DiagnosisMessage, DiagnosisPreview]:
        """Re-derive the preview from the current transcript + session state,
        without a chat turn. Used by select-option / business-profile: one
        extraction call for a discrete visitor action, not per turn."""
        history = await self.repository.list_messages(session.id)
        if not history:
            raise ValidationDomainError("A conversa ainda não começou")
        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]
        governance = await self.get_governance()
        extraction = await self._extract(
            llm_messages, max_tokens=governance.diagnosis_max_output_tokens
        )
        turn_metrics = await self.repository.list_turn_metrics(session.id)
        preview = self._preview(
            extraction,
            grounded=any(tm.chunks_used_count > 0 for tm in turn_metrics),
            session=session,
        )
        await self._persist_turn_state(session, preview)
        last_assistant = next((m for m in reversed(history) if m.role == "assistant"), history[-1])
        return last_assistant, preview

    async def select_option(
        self, *, session_id: uuid.UUID, option_key: str
    ) -> tuple[DiagnosisMessage, bool, DiagnosisPreview]:
        session = await self.repository.get_session(session_id)
        keys = {o.get("key") for o in session.options_snapshot}
        if option_key not in keys:
            raise ConflictError(
                f"Option {option_key!r} is not among the proposed paths for this session"
            )
        chosen = next(o for o in session.options_snapshot if o.get("key") == option_key)
        await self.repository.update_session(session, selected_option_key=option_key)
        confirmation = await self.repository.add_message(
            diagnosis_session_id=session_id,
            role="assistant",
            content=(
                f"Boa escolha — vou seguir com “{chosen.get('title')}”. "
                "Agora me confirma alguns dados do negócio para eu fechar a cotação."
            ),
        )
        _last, preview = await self._recompute_preview(session)
        return confirmation, preview.stage == "ready", preview

    async def patch_business_profile(
        self, *, session_id: uuid.UUID, patch: BusinessProfilePatch
    ) -> tuple[DiagnosisMessage, bool, DiagnosisPreview]:
        session = await self.repository.get_session(session_id)
        merged = dict(session.business_profile)
        merged.update(patch.model_dump(exclude_unset=True))
        await self.repository.update_session(session, business_profile=merged)
        last_assistant, preview = await self._recompute_preview(session)
        return last_assistant, preview.stage == "ready", preview

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

    async def submit(
        self, *, session_id: uuid.UUID, body: DiagnosisSubmitRequest | None = None
    ) -> DiagnosisRequest:
        """Contact details (name/email/phone/company/cnpj) come from the
        conversation's own extraction and the collected business profile, not
        as a separate signup form. `body` (ADR-0004) carries last-chance
        overrides for the chosen path and the profile.

        Uses the FULL transcript (not the fixed per-turn window) -- this is a
        one-time call at the end of the session, not a per-turn cost driver,
        and the final extraction/record benefits from seeing everything.
        """
        diagnosis_session = await self.repository.get_session(session_id)
        history = await self.repository.list_messages(session_id)
        if not history:
            raise ValidationDomainError("Cannot submit a diagnosis request with no conversation")

        # Overlay any explicit overrides onto the session before recomputing.
        session_updates: dict[str, object] = {}
        if body and body.selected_option_key:
            if body.selected_option_key not in {
                o.get("key") for o in diagnosis_session.options_snapshot
            }:
                raise ConflictError(
                    f"Option {body.selected_option_key!r} is not among the proposed paths"
                )
            session_updates["selected_option_key"] = body.selected_option_key
        if body and body.business_profile is not None:
            merged = dict(diagnosis_session.business_profile)
            merged.update(body.business_profile.model_dump(exclude_unset=True))
            session_updates["business_profile"] = merged
        if session_updates:
            diagnosis_session = await self.repository.update_session(
                diagnosis_session, **session_updates
            )

        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]
        governance = await self.get_governance()
        extraction = await self._extract(
            llm_messages, max_tokens=governance.diagnosis_max_output_tokens
        )
        turn_metrics = await self.repository.list_turn_metrics(session_id)
        preview = self._preview(
            extraction,
            grounded=any(tm.chunks_used_count > 0 for tm in turn_metrics),
            session=diagnosis_session,
        )
        if preview.stage != "ready":
            raise ValidationDomainError(
                "Not enough information has been gathered yet to submit a diagnosis request"
            )

        possibly_ungrounded = not any(tm.chunks_used_count > 0 for tm in turn_metrics)
        effective = _effective_profile(extraction, dict(diagnosis_session.business_profile))

        diagnosis_request = await self.repository.create_request(
            diagnosis_session_id=diagnosis_session.id,
            contact_name=cast(str | None, effective.get("contact_name")),
            contact_email=cast(str | None, effective.get("contact_email")),
            contact_phone=cast(str | None, effective.get("contact_phone")),
            company_name=cast(str | None, effective.get("business_name")),
            cnpj=extraction.cnpj,
            problem_summary=extraction.problem_summary,
            services_of_interest=extraction.services_of_interest,
            budget_range=preview.budget_range,
            timeline=preview.timeline,
            selected_option_key=diagnosis_session.selected_option_key,
            business_profile=preview.business_profile.model_dump(),
            raw_transcript_snapshot=[{"role": m.role, "content": m.content} for m in history],
            possibly_ungrounded=possibly_ungrounded,
        )
        await self.repository.mark_completed(diagnosis_session)
        return diagnosis_request

    async def list_requests(self) -> list[DiagnosisRequest]:
        return await self.repository.list_requests()
