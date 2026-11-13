# Project Foundation

The application is a monorepo with a Next.js frontend and a FastAPI backend.
The backend owns the API and exposes a health check at `/health`. The frontend
is served on port 3000 and calls the backend through its configured API base URL.

Kubernetes inspection, AI reasoning, authentication, and persistent storage are
intentionally placeholders at this stage.
