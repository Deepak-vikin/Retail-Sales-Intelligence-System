# Backend Application Service

FastAPI-powered backend for the Retail Sales Intelligence Platform.

## Directory Layout

```text
backend/
├── app/
│   ├── main.py          # FastAPI application entrypoint
│   ├── api/              # API router endpoints
│   ├── services/         # Business logic layer
│   ├── database/         # Database connection and core config
│   ├── models/           # Data models & schemas
│   ├── ai/               # AI reasoning, Text-to-SQL, and routing
│   │   ├── text_to_sql/
│   │   ├── rag/
│   │   └── query_router/
│   └── core/             # Core settings and database clients
├── tests/                # Unit, integration, and e2e test suite
├── requirements.txt      # Backend Python dependencies
└── pytest.ini            # Pytest configuration
```

## Running Locally

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure `.env` is configured with `DATABASE_URL` and `OPENROUTER_API_KEY`.

4. Start the backend:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   Or from the repository root:
   ```bash
   uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. Run tests:
   ```bash
   pytest tests/unit -v
   ```

