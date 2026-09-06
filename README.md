# One School — Scheduling & Attendance SaaS

A production-ready full-stack platform for managing classes, instructors, students, attendance, cancellations, replacement credits, and automated reminders from a single administrative dashboard.

> **Portfolio case study:** the live production environment requires authentication and contains private client data, so public demo credentials and production screenshots are intentionally not included.

## Product overview

One School replaces fragmented spreadsheets and manual follow-ups with a centralized workflow for daily school operations. Administrators can organize recurring classes, monitor attendance, manage cancellations and replacement credits, and keep students informed through calendar and WhatsApp integrations.

### Core capabilities

- Class calendar with recurring schedules and status tracking
- Student, instructor, and class management
- Attendance history and frequency reporting
- Cancellation rules and replacement-credit lifecycle
- Google Calendar synchronization
- Automated WhatsApp reminders through Evolution API
- Role-protected administrative access
- Background jobs for operational automation
- Responsive React dashboard
- Automated backend tests

## Architecture

```text
React + TypeScript + Vite
          |
          v
     FastAPI REST API
          |
    +-----+--------------+
    |                    |
    v                    v
PostgreSQL         External services
SQLAlchemy         Google Calendar
                   Evolution API / WhatsApp
```

The FastAPI application also serves the production frontend build from `frontend/dist`, allowing the project to run as a single deployable service.

## Tech stack

| Area | Technologies |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Pydantic |
| Frontend | React, TypeScript, Vite |
| Database | PostgreSQL |
| Integrations | Google Calendar API, Evolution API / WhatsApp |
| Quality | Pytest, automated backend tests |
| Deployment | Render, Uvicorn |

## Repository structure

```text
.
├── backend/
│   ├── app/             # API routes, business rules, services and jobs
│   └── tests/           # Automated backend tests
├── frontend/
│   ├── src/             # React application
│   └── dist/            # Production build served by FastAPI
├── migrations/          # Database updates for existing environments
├── .env.example         # Safe configuration template
├── pytest.ini
├── render.yaml
└── requirements.txt
```

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL

### 1. Configure the environment

```bash
cp .env.example .env
```

Fill the variables in `.env` with your own development credentials. Never commit the completed file.

### 2. Install and build

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm ci
npm run build
cd ..
```

On Windows, activate the virtual environment with `.venv\\Scripts\\activate`.

### 3. Run the application

```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/login`.

## Tests

```bash
python -m pytest -q
cd frontend && npm run build
```

## Deployment notes

The repository includes `render.yaml`. Existing manually configured Render services should keep the repository root as the root directory and use:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
```

The committed `frontend/dist` directory supports Python-only deployment environments. Rebuild it whenever files under `frontend/src` change.

## Privacy and security

- Production credentials belong only in environment variables.
- `.env` and credential files are excluded from version control.
- Production access is restricted to authorized users.
- Client and student information is intentionally excluded from this public repository.
- Please report security concerns privately instead of opening a public issue.

## Author

**João Gabriel Vieira Barbosa**  
Full-Stack Developer focused on Python, FastAPI, React, APIs, and business automation.

[GitHub profile](https://github.com/JoaoGabriel39359)
