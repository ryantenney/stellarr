# Contributing to Overseer Lite

Thank you for your interest in contributing to Overseer Lite!

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up your development environment (see below)
4. Create a branch for your changes

## Development Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- Docker (optional, for self-hosted backend)
- AWS CLI (optional, for Lambda deployment)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `localhost:5173` and proxies API requests to `localhost:8000`.

### Backend (Docker)

```bash
cp .env.example .env
# Edit .env with your TMDB API key and other settings
docker compose up -d
```

### Backend (Local Python)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Project Structure

- `frontend/` - SvelteKit SPA
- `backend/` - FastAPI + SQLite (Docker/self-hosted)
- `backend-lambda/` - FastAPI + DynamoDB (AWS serverless)
- `terraform/` - AWS infrastructure as code

**Important:** Both backend implementations must stay in sync. If you modify API endpoints, update both `backend/main.py` and `backend-lambda/main.py`.

## Making Changes

### Code Style

- Frontend: Follow existing Svelte patterns, use `npm run build` to check for errors
- Backend: Follow PEP 8, use type hints where practical

### Commit Messages

Write clear, concise commit messages describing what changed and why.

### Pull Requests

1. Ensure your code builds without errors
2. Test your changes locally
3. Update documentation if needed
4. Submit a PR with a clear description of the changes

## Reporting Issues

When reporting bugs, please include:

- Steps to reproduce
- Expected vs actual behavior
- Browser/environment details
- Relevant logs or screenshots

## Questions?

Open an issue for questions or discussion about potential changes.
