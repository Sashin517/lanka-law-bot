import asyncio
import os
import argparse
from dotenv import load_dotenv

load_dotenv()

from langsmith import Client
from langsmith.evaluation import evaluate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from app.agent import process_query_with_route

# Initialize LangSmith client
client = Client()

# Initialize LLM for Evaluation (LLM-as-a-judge)
eval_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash", 
    temperature=0, 
    google_api_key=os.environ.get("GOOGLE_API_KEY")
)

correctness_prompt = PromptTemplate.from_template(
    """You are an expert legal evaluator grading a legal assistant's answer.
    
    Question: {input}
    Ground Truth Answer: {expected}
    Generated Answer: {output}
    
    Is the Generated Answer factually correct and aligned with the Ground Truth Answer? 
    It doesn't need to be word-for-word, but the core legal facts must be accurate.
    
    Score 1 for Yes (Correct), 0 for No (Incorrect).
    Respond with ONLY the number 1 or 0.
    """
)

def correctness_evaluator(run, example):
    """Evaluates if the response is factually correct compared to the expected answer."""
    question = example.inputs.get("question")
    expected_answer = example.outputs.get("expected_answer", "")
    
    # Run output contains a 'LegalResponse' dict based on our pipeline
    # The actual output is usually stored in run.outputs
    generated_answer = run.outputs.get("answer", "")
    
    if not expected_answer:
        return {"key": "correctness", "score": None, "comment": "No ground truth provided"}

    chain = correctness_prompt | eval_llm
    result = chain.invoke({
        "input": question,
        "expected": expected_answer,
        "output": generated_answer
    })
    
    try:
        score = float(result.content.strip())
        return {"key": "correctness", "score": score}
    except ValueError:
        return {"key": "correctness", "score": 0.0, "comment": "Failed to parse judge output"}

async def target_function(inputs: dict) -> dict:
    """The function we are testing in LangSmith."""
    question = inputs["question"]
    response, _ = await process_query_with_route(question)
    return {"answer": response.summary}

def main():
    parser = argparse.ArgumentParser(description="Evaluate LankaLawBot RAG pipeline")
    parser.add_argument("--dataset", type=str, required=True, help="Name of the LangSmith dataset to evaluate against")
    args = parser.parse_args()
    
    print(f"Starting evaluation on dataset: {args.dataset}...")
    
    results = evaluate(
        target_function,
        data=args.dataset,
        evaluators=[correctness_evaluator],
        experiment_prefix="legal-rag-eval",
        max_concurrency=2, # Keep low to respect rate limits
    )
    
    print("Evaluation triggered successfully. View results in your LangSmith dashboard.")

if __name__ == "__main__":
    asyncio.run(main())
