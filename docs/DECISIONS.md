# Decisions

## D-001: Deployment target

The target environment is an Ubuntu VPS. The beta will use a simple direct Node.js and Python deployment; containerization and other production deployment concerns are deferred. No macOS-specific paths, services, or tooling are part of the application design.

## D-002: Initial repository shape

The project uses a frontend/backend monorepo:

- Frontend: Next.js, React, TypeScript, Tailwind CSS.
- Backend: FastAPI, Python, Pydantic.

## D-003: Phase 0 scope

Phase 0 establishes service structure, configuration, and health verification. Authentication, TiDB, Cloudflare R2, background jobs, AI, computer vision, and presentation processing begin in subsequent phases.
