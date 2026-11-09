import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent

env_paths = [
    BASE_DIR / ".env",
    ROOT_DIR / ".env",
]
for env_path in env_paths:
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path)
        break
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PRIMARY_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_URL:
    project_id = "cxlhcpxozqtmpiiuxtat"
    SUPABASE_URL = f"https://{project_id}.supabase.co"

SUPABASE_JWKS_URL = os.getenv(
    "SUPABASE_JWKS_URL",
    f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
)

SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", None)

# Separate dedicated bootstrap secret for initial owner creation
# Never reuses the Supabase service role key.
BOOTSTRAP_SECRET = os.getenv("BOOTSTRAP_SECRET", "")
