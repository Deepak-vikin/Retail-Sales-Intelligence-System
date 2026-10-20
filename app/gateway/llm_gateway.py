import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class LLMGateway:

    def __init__(self):

        self.client = OpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=60.0,
            max_retries=2
        )

        self.models = list(
            dict.fromkeys([
                os.getenv(
                    "PRIMARY_MODEL",
                    "nvidia/nemotron-3-ultra:free"
                ),
                os.getenv(
                    "FALLBACK_MODEL",
                    "nvidia/nemotron-3-super:free"
                ),
                os.getenv(
                    "FALLBACK_MODEL_2",
                    "google/gemma-4-31b-it:free"
                ),
                os.getenv(
                    "FALLBACK_MODEL_3",
                    "nvidia/nemotron-3.5-lightning:free"
                )
            ])
        )

    def _call(self, model, prompt):

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        message = response.choices[0].message

        content = getattr(message, "content", None)

        if not content:
            raise RuntimeError(
                f"Model {model} returned empty content."
            )

        content = content.strip()

        if content.lower().startswith("user safety:"):
            raise RuntimeError(
                f"Model {model} returned an invalid safety response: "
                f"{content}"
            )

        return content

    def complete(self, prompt):

        errors = []

        for model in self.models:

            try:
                print(f"LLM: Trying {model}")

                answer = self._call(model, prompt)

                print(f"LLM: Success with {model}")

                return answer

            except Exception as error:

                print(f"LLM: Failed {model}")

                errors.append(
                    f"{model}: {error}"
                )

        raise RuntimeError(
            "All LLM models failed.\n"
            + "\n".join(errors)
        )