# Architecture

## Foundation

The repository is a two-service application:

- `frontend/`: Next.js, React, TypeScript, and Tailwind CSS.
- `backend/`: FastAPI and Pydantic settings.

During beta development, both services run directly from their project directories. The frontend uses port 3000 and the API uses port 8000.

## Planned boundaries

The specification requires provider-independent adapters for object storage, PPTX extraction/rendering, AI models, pose inference, speech transcription, pronunciation, and background jobs. These are intentionally not implemented in the Phase 0 scaffold.

## Security baseline

Configuration is environment-based. Secrets are excluded from Git. The backend exposes only a health endpoint and applies a narrow initial CORS policy using `FRONTEND_URL`.
