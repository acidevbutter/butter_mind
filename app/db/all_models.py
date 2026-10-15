"""Imports every domain's models module so Base.metadata sees all tables —
required for Alembic autogenerate to detect the full schema.
"""

from app.chat import models as chat_models  # noqa: F401
from app.diagnosis import models as diagnosis_models  # noqa: F401
from app.emails import models as emails_models  # noqa: F401
from app.knowledge import models as knowledge_models  # noqa: F401
from app.llm_usage import models as llm_usage_models  # noqa: F401
from app.sender_domains import models as sender_domains_models  # noqa: F401
from app.tenants import models as tenants_models  # noqa: F401
