# Jobyro

AI resume builder project scaffolded from the engineering handoff.

## Structure

```text
backend/   FastAPI app, schemas, services, tests
frontend/  Vite React app
infra/     Docker Compose and environment examples
```

## Add your API key

Edit `.env` at the project root:

```env
OPENAI_API_KEY=your_key_here
```

Do not commit `.env`.

## Run locally

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Postgres with Docker:

```powershell
cd infra
docker compose up postgres
```

Run migrations after Postgres is up:

```powershell
cd backend
alembic upgrade head
```

## Resume generation format

The backend generation contract is encoded in:

- `backend/app/schemas/resume.py`
- `backend/app/services/resume_generation_contract.py`

`POST /api/resumes/generate` accepts a `candidate_profile` shaped like the resume format spec and returns ATS-safe structured content plus a deterministic layout contract. If the UI does not send a profile yet, the backend uses a sample Venu profile as a temporary fallback.
