# 🛍️ Retail Sales Intelligence Platform

AI-powered retail intelligence and barcode-ready billing platform combining operational management with natural language business queries via Text-to-SQL and RAG.

---

## 🗂️ Target Project Structure

```text
Retail-Sales-Intelligence/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── Services/
│   │   ├── core/
│   │   ├── ai/
│   │   ├── rag/
│   │   ├── ingestion/
│   │   ├── jobs/
│   │   └── gateway/
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── requirements.txt
│   ├── pytest.ini
│   └── README.md
│
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
│
├── ingestion/
│   ├── csv/
│   └── scripts/
│
├── scripts/
│   └── schema.py
│
├── .env
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

## 🚀 Running Locally

### 1. Prerequisites
- Python 3.10+
- PostgreSQL / Supabase account
- OpenRouter API key

### 2. Environment Setup

Create `.env` in the root directory (or `backend/.env`) based on `.env.example`:

```bash
cp .env.example .env
```

Populate the required environment keys:
- `DATABASE_URL` (Supabase PostgreSQL connection string)
- `OPENROUTER_API_KEY` (OpenRouter API key for LLM gateway)

### 3. Backend Setup

```bash
# Activate your virtual environment
.\venv\Scripts\Activate.ps1  # Windows PowerShell
# or: source venv/bin/activate (Linux/macOS)

# Install dependencies
pip install -r backend/requirements.txt

# Start backend server
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Alternatively, from the repository root:
```bash
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- API Docs: `http://127.0.0.1:8000/docs`
- Root Info: `http://127.0.0.1:8000/`
- Frontend UI via FastAPI: `http://127.0.0.1:8000/app`

### 4. Frontend Setup

The frontend is served directly through FastAPI at `http://127.0.0.1:8000/app`, or can be opened directly or served statically:

```bash
cd frontend
python -m http.server 3000
```
Open `http://127.0.0.1:3000` in your web browser.

---

## 🧪 Running Tests

Run all unit tests:
```bash
pytest backend/tests/unit -v
```

Or from the backend directory:
```bash
cd backend
pytest tests/unit -v
```
