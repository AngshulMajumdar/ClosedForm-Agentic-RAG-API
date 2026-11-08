"""Bounded-concurrency client integration. Each answer may incur real charges."""
import asyncio
from closedform_rag import AsyncClosedFormRAGClient

QUESTIONS = [
    "What city is the capital of Japan?",
    "What is a stochastic process?",
    "What is retrieval-augmented generation?",
]

async def main():
    async with AsyncClosedFormRAGClient() as client:
        results = await client.batch_answer(
            QUESTIONS,
            budgets={"max_llm_calls":2,"max_retrieval_calls":2,"deadline_ms":25000},
            concurrency=2,
            return_exceptions=True,
        )
        for question, result in zip(QUESTIONS, results):
            if isinstance(result, Exception):
                print(question, "ERROR:", str(result))
            else:
                print(question, "=>", result.get("answer"), result.get("selected_action"))

if __name__ == "__main__":
    asyncio.run(main())
