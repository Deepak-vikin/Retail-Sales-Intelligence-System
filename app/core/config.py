import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL=os.getenv("DATABASE_URL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PRIMARY_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
