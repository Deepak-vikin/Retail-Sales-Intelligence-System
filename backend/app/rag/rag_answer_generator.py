from app.gateway.llm_gateway import LLMGateway


class RAGAnswerGenerator:
    def __init__(self):
        self.gateway = LLMGateway()

    def generate_answer(self, question, documents):
        context = "\n\n".join(
            document[0] for document in documents
        )

        prompt = f"""
You are a retail knowledge assistant.

User question:
{question}

Retrieved knowledge:
{context}

Rules:
- Answer using only the retrieved knowledge.
- Do not invent information.
- If the retrieved knowledge does not contain the answer, say that the information is not available.
- Be concise and clear.

Answer:
"""

        return self.gateway.complete(prompt).strip()