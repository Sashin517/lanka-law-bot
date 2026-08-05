"""
Custom LLM-as-a-Judge Metrics for Generative Legal Tasks.
Follows production-grade evaluation patterns for non-deterministic text generation.
"""
import json
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel

class DraftingRubricEvaluator:
    """
    Evaluates a generated legal draft against a natural language rubric 
    and the retrieved legal context.
    """
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        
        # System prompt designed to force strict adherence to the rubric
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert Sri Lankan Legal Evaluator. 
Your job is to evaluate a generated contract draft against a specific set of requirements (Rubric).

You must output your evaluation in STRICT JSON format with exactly two keys:
1. "score": A float between 0.0 (complete failure) and 1.0 (perfectly meets all requirements).
2. "reasoning": A brief explanation of why this score was given.

Scoring Guidelines:
- 1.0: Draft includes all rubric requirements and uses professional legal boilerplate.
- 0.5: Draft includes some requirements but misses critical elements.
- 0.0: Draft completely ignores the rubric or hallucinates invalid laws."""),
            ("human", """
=== RETRIEVED LEGAL STATUTES ===
{context}

=== RUBRIC / REQUIREMENTS ===
{rubric}

=== GENERATED DRAFT ===
{draft}

Evaluate the generated draft. Output JSON only:""")
        ])

    async def a_evaluate_sample(self, draft: str, rubric: str, contexts: list[str]) -> Dict[str, Any]:
        """Async evaluation of a single sample."""
        context_str = "\n\n".join(contexts) if contexts else "No legal context provided."
        
        chain = self.prompt | self.llm
        
        try:
            response = chain.invoke({
                "context": context_str,
                "rubric": rubric,
                "draft": draft
            })
            
            raw_output = response.content
            if isinstance(raw_output, list):
                if len(raw_output) > 0 and isinstance(raw_output[0], dict) and "text" in raw_output[0]:
                    raw_output = raw_output[0]["text"]
                else:
                    raw_output = str(raw_output[0])
            elif not isinstance(raw_output, str):
                raw_output = str(raw_output)
            
            raw_output = raw_output.strip()
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:]
            elif raw_output.startswith("```"):
                raw_output = raw_output[3:]
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3]
            
            raw_output = raw_output.strip()
            result = json.loads(raw_output)
            
            return {
                "score": float(result.get("score", 0.0)),
                "reasoning": result.get("reasoning", "No reasoning provided.")
            }
        except Exception as e:
            return {"score": 0.0, "reasoning": f"Evaluation parsing failed: {str(e)}"}

    def evaluate_sample(self, draft: str, rubric: str, contexts: list[str]) -> Dict[str, Any]:
        """Synchronous evaluation of a single sample."""
        context_str = "\n\n".join(contexts) if contexts else "No legal context provided."
        
        chain = self.prompt | self.llm
        
        try:
            response = chain.invoke({
                "context": context_str,
                "rubric": rubric,
                "draft": draft
            })
            
            raw_output = response.content
            if isinstance(raw_output, list):
                if len(raw_output) > 0 and isinstance(raw_output[0], dict) and "text" in raw_output[0]:
                    raw_output = raw_output[0]["text"]
                else:
                    raw_output = str(raw_output[0])
            elif not isinstance(raw_output, str):
                raw_output = str(raw_output)
                
            raw_output = raw_output.strip()
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:]
            elif raw_output.startswith("```"):
                raw_output = raw_output[3:]
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3]
                
            raw_output = raw_output.strip()
            result = json.loads(raw_output)
            
            return {
                "score": float(result.get("score", 0.0)),
                "reasoning": result.get("reasoning", "No reasoning provided.")
            }
        except Exception as e:
            return {"score": 0.0, "reasoning": f"Evaluation parsing failed: {str(e)}"}
