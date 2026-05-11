"""Prompt for the Quick QA agent.

Re-exports the existing grounded RAG prompt.  Kept as a separate module
so future tuning or A/B tests can diverge without touching the shared
``app.prompts.legal_rag`` template.
"""

from app.prompts.legal_rag import LEGAL_RAG_SYSTEM_PROMPT

# Re-export under the agent-specific name
QUICK_QA_PROMPT = LEGAL_RAG_SYSTEM_PROMPT
