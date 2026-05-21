import asyncio
import json
import logging
from typing import List

# Setup simple logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.agents.nodes.router_node").setLevel(logging.INFO)

from evaluation.eval_pipeline import run_pipeline

QUESTIONS = [
    "A seller of agricultural produce verbally demands that a buyer take delivery by Friday. However, on that Friday, the goods are securely locked in a warehouse in a different district, not at the agreed place of delivery. If the seller sues for damages for non-acceptance, how would the court evaluate the seller's claim under Rawanna & Co. v. Arunachapillai?",
    "A vendor agrees to sell a commercial property to a buyer but subsequently negotiates to sell it to a third party for a higher price. The original buyer seeks an interim injunction to prevent the sale to the third party pending a specific performance suit. Based on Roberts v. Ratnayake, what legal standards must the buyer satisfy to obtain this equitable relief?",
    "How do the requirements of Section 2 of the Prevention of Frauds Ordinance intersect with the licensing requirements of the Notaries Ordinance to determine the validity of a deed of transfer, and what is the effect on its registration?",
    "Draft a letter of demand from a beneficiary (seller) to an issuing bank demanding immediate payment under an irrevocable Letter of Credit, asserting the autonomy principle from Hatton National Bank v. Sellers Sports after the bank wrongfully withheld payment due to the buyer's complaints about the shipped goods.",
]


async def run_production_test():
    print("Running Production Pipeline (LangGraph)...")
    print("=" * 80)

    for i, question in enumerate(QUESTIONS, 1):
        print(f"\n--- Question {i} ---")
        print(f"Query: {question}")

        # Run through the actual production LangGraph pipeline
        # Using deep_research mode to simulate a complex query
        state = await run_pipeline(question=question, mode="quick_qa")

        years = state.get("year_filter")
        acts = state.get("act_name_filter")
        route = state.get("route")

        print(f"Routed to      : {route}")
        print(f"Filters Applied: Years={years}, Acts={acts}")

        sources = state.get("retrieved_sources", [])

        if not sources:
            print("  -> NO RESULTS FOUND.")

        print(f"Retrieved {len(sources)} chunks from production graph:")
        for idx, source in enumerate(sources, 1):
            title = (
                source.get("title", "Unknown Title")
                if isinstance(source, dict)
                else getattr(source, "title", "Unknown Title")
            )
            year = (
                source.get("year", "N/A")
                if isinstance(source, dict)
                else getattr(source, "year", "N/A")
            )
            score = (
                source.get("relevance_score", 0.0)
                if isinstance(source, dict)
                else getattr(source, "relevance_score", 0.0)
            )
            print(f"  [{idx}] Score: {score:.3f} | Title: '{title}' ({year})")


if __name__ == "__main__":
    asyncio.run(run_production_test())
