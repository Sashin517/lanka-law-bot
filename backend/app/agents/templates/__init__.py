"""Legal document templates for the Drafting agent.

Each template provides a structural skeleton that the LLM fills in
using retrieved legal context and user-provided facts.
"""

from app.agents.templates.contract import CONTRACT_TEMPLATE
from app.agents.templates.pleading import PLEADING_TEMPLATE
from app.agents.templates.notice import NOTICE_TEMPLATE
from app.agents.templates.affidavit import AFFIDAVIT_TEMPLATE

# Template registry — keyed by answer_mode / document type
TEMPLATE_REGISTRY: dict[str, str] = {
    "contract": CONTRACT_TEMPLATE,
    "pleading": PLEADING_TEMPLATE,
    "notice": NOTICE_TEMPLATE,
    "affidavit": AFFIDAVIT_TEMPLATE,
}

__all__ = [
    "TEMPLATE_REGISTRY",
    "CONTRACT_TEMPLATE",
    "PLEADING_TEMPLATE",
    "NOTICE_TEMPLATE",
    "AFFIDAVIT_TEMPLATE",
]
