# Veridia – AI-Powered Dashboard Generator

> Upload any CSV dataset, describe what you want, and get a fully interactive Plotly-Dash dashboard in minutes – no coding required.

---

## Table of Contents
- [Quick Start (Local)](#quick-start-local)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Running with Docker](#running-with-docker)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)

---

## Quick Start (Local)

### Prerequisites
| Tool | Version |
|------|---------|
| Node.js | 18 or 20 |
| Python | 3.10 – 3.12 |
| npm | ≥ 9 |

### 1 – Clone & configure environment

```bash
git clone <repo-url>
cd viz.ai-main
```

**Backend secrets (required)**

```bash
cp backend/.env.example backend/.env.local
# Open backend/.env.local and add your GROQ_API_KEY
```

**Frontend (optional – only needed for production builds pointing at a remote backend)**

```bash
cp .env.example .env.local
# Edit .env.local only if your backend is NOT on localhost:8000
```

### 2 – Install & run the backend

```bash
cd backend
pip install -r requirements.txt
python start_backend.py
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 3 – Install & run the frontend (separate terminal)

```bash
# From the project root
npm install
npm run dev
# Frontend available at http://localhost:5173
```

> **Tip:** The Vite dev server automatically proxies all `/api/*` requests to the backend at `http://127.0.0.1:8000`, so you don't need to set `VITE_API_BASE_URL` for local development.

### 4 – Build for production

```bash
npm run build        # outputs to dist/
npm run preview      # serve dist/ locally to verify
```

---

## Environment Variables

### Backend (`backend/.env.local`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | **Yes** | – | Groq API key for LLM calls. Get one at [console.groq.com](https://console.groq.com) |
| `GEMINI_API_KEY` | No | – | Google Gemini API key for optional enrichment |
| `UPLOAD_DIR` | No | `backend/uploads` | Directory for uploaded CSV files |
| `DASHBOARD_DIR` | No | `backend/generated_dashboards` | Directory for generated dashboard scripts |
| `CHROMA_DIR` | No | `backend/chroma_db` | ChromaDB vector store path |
| `R_OUTPUT_DIR` | No | `backend/generated_visualization` | R visualization output path |
| `CORS_ORIGINS` | No | `*` | Comma-separated allowed CORS origins |
| `BACKEND_PORT` | No | `8000` | Port uvicorn listens on |

### Frontend (`.env.local` at project root)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | No | `http://127.0.0.1:8000` | Full URL of the backend API. Leave unset for local dev (proxy handles it). |

---

## Project Structure

```
viz.ai-main/
├── backend/                  # FastAPI backend
│   ├── app/
│   │   ├── main.py           # FastAPI app, routes
│   │   ├── paths.py          # Portable path constants
│   │   └── services/
│   │       ├── config.py
│   │       ├── prompt_chain_new.py   # Dash/Plotly generation pipeline
│   │       └── prompt_chain_R.py     # R/animint2 pipeline
│   ├── data/                 # Sample CSV datasets (committed)
│   ├── requirements.txt
│   ├── start_backend.py      # Startup script
│   └── .env.example          # ← copy to .env.local and fill in
├── src/                      # React/Vite frontend source
│   ├── components/
│   │   └── DataVisualizationAgent.tsx  # Main UI
│   └── services/
│       └── api.ts            # Backend API client
├── frontend/
│   ├── Dockerfile            # Frontend container
│   └── nginx.conf            # SPA routing for production
├── .env.example              # Frontend env template
├── .gitignore
├── .dockerignore
├── docker-compose.yml
├── package.json
└── vite.config.ts            # Dev proxy: /api → localhost:8000
```

---

## Running with Docker

```bash
# 1. Set your API key
cp backend/.env.example backend/.env.local
#    Edit backend/.env.local – set GROQ_API_KEY

# 2. (Optional) override ports or CORS in your shell or a root .env
export BACKEND_PORT=8000
export FRONTEND_PORT=8080
export CORS_ORIGINS="http://localhost:8080"

# 3. Build and start
docker-compose up --build -d

# 4. View logs
docker-compose logs -f

# 5. Stop
docker-compose down
```

Services after startup:
- Frontend: http://localhost:8080
- Backend API: http://localhost:8000
- Backend docs: http://localhost:8000/docs

---

## Architecture

```
Browser (React/Vite)
    │  API calls to /api → proxied to FastAPI in dev
    ▼
FastAPI Backend (Python 3.11)
    ├── /upload-dataset     → saves CSV to UPLOAD_DIR
    ├── /generate-dashboard → starts background generation pipeline
    ├── /dashboard-status   → polls generation progress
    ├── /run-dashboard      → launches Dash subprocess
    ├── /chat-edit          → AI-powered code editing
    └── /update-code        → manual code edit + rerun
            │
            ▼
    prompt_chain_new.py (Groq LLM pipeline)
    Stage 1 – Dataset analysis      (llama-4-scout)
    Stage 2 – Dashboard design      (gpt-oss-20b)
    Stage 3 – Code generation       (gpt-oss-120b)
    Stage 4 – Code optimization     (deepseek-r1)
    Stage 5 – Auto-fix if errors    (deepseek-r1)
    Stage 6 – Launch Dash subprocess
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `GROQ_API_KEY … not configured` | Add your key to `backend/.env.local` |
| Frontend can't reach backend | Ensure backend is on port 8000; in dev the Vite proxy handles routing |
| `numpy.dtype size changed` error | Run `pip install -U pandas numpy` |
| Dashboard subprocess fails | Check `/dashboard-error/{id}` endpoint; click "Attempt Auto-Fix" in UI |
| Port already in use | Set `BACKEND_PORT=8001` in `backend/.env.local` |
| ChromaDB import error on first run | Run `pip install chromadb sentence-transformers` |