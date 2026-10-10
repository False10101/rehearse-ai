# Rehearse AI

AI-powered presentation coaching for university students. The application will analyze PowerPoint decks, help improve presentation scripts, and provide privacy-conscious rehearsal feedback.

## Current status

Phase 0 foundation: a Next.js frontend, FastAPI backend, and environment template. Product features are intentionally not implemented yet.

## Prerequisites

- Node.js 22+
- Python 3.12+

## Local development

1. Create local configuration:

   ```sh
   cp .env.example .env
   ```

2. Install frontend dependencies:

   ```sh
   npm install
   ```

3. Install backend dependencies:

   ```sh
   cd backend
   python3 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

4. Start the services in separate terminals:

   ```sh
   cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
   npm run dev
   ```

The frontend is available at `http://localhost:3000`; API health is available at `http://localhost:8000/health`.

## Checks

```sh
npm run lint
npm run typecheck
npm run test
cd backend && .venv/bin/ruff check . && .venv/bin/pytest
```
