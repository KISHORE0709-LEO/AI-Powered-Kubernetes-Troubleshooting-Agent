# AI Kubernetes Troubleshooting Agent - High Level Design (HLD)

## Getting Started

This repository contains a FastAPI API and a Next.js dashboard. The dashboard
uses InsForge authentication, realtime investigation progress, and per-user
investigation history. The backend includes a read-only Kubernetes evidence
collector and an OpenRouter-powered diagnosis layer.

### Run with Docker Compose

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000) for the dashboard and
[http://localhost:8000/health](http://localhost:8000/health) for the API health
check.

Copy `.env.example` to `.env` and set `NEXT_PUBLIC_INSFORGE_URL`,
`NEXT_PUBLIC_INSFORGE_ANON_KEY`, and `INSFORGE_URL` for the linked InsForge
project. The dashboard requires InsForge credentials; Kubernetes access is
optional for starting the app. To let the Dockerized
backend read your local kubeconfig, set `KUBECONFIG_HOST_PATH` to its absolute
path and start the optional kubeconfig Compose file:

```powershell
$env:KUBECONFIG_HOST_PATH = "$env:USERPROFILE\.kube\config"
docker compose -f docker-compose.yml -f docker-compose.kubeconfig.yml up --build
```

The kubeconfig is mounted read-only. The API and frontend ports bind to
localhost. `/investigate` exposes cluster metadata and a limited, redacted
selection of pod logs. Use a Kubernetes context with read-only RBAC permissions.

### Kubernetes Investigation API

`POST /investigate` requires a user bearer token and the ID of an owned,
running history row. The dashboard creates that row before sending the request.
The API collects pod health, relevant logs, warning events,
deployment availability, and service endpoint/selector evidence using
read-only `kubectl` commands, then asks OpenRouter to correlate the evidence.
On success, the response contains the collected `investigation` and a
`diagnosis` with the root cause, explanation, fix, a suggested `kubectl_command`,
prevention recommendation, and confidence score. Suggested commands are not
executed. If cluster access, AI configuration, or the AI provider fails, the
endpoint returns an error response instead of a success-shaped diagnosis.

Kubectl commands have a timeout and output limit; pod log collection is capped
and redacts common credential formats. The AI prompt also treats collected text
as untrusted data and redacts common secret assignments. The endpoint rejects
requests without an authenticated session and verifies history ownership.

Configure `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in the root `.env` for
Docker Compose, or in `backend/.env` for local backend development. Keep the
key server-side; never use a `NEXT_PUBLIC_` variable. The InsForge CLI can
provision the Model Gateway key with `npx -y @insforge/cli ai setup` when the
organization's plan supports AI. In this linked project, that command reports
that AI is available only on paid plans; upgrade the InsForge organization or
provide an OpenRouter key through the backend environment before running an
AI-backed investigation.

The history schema and realtime policies are defined in
`migrations/20261112192859_investigation-history.sql`. They were applied to the
isolated `dashboard-history` InsForge branch; the migration has not been merged
to the parent project. Use that branch's URL and anon key in local environment
files while testing. Review the migration and explicitly merge the branch
before using this integration against the parent project.

### Run locally

Start the backend from `backend/`:

```bash
python -m venv .venv
# Activate the virtual environment, then:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For local environment overrides, copy `backend/.env.example` to `backend/.env`
and set `INSFORGE_URL` to the linked project's URL. The frontend reads
`frontend/.env.local`; copy `frontend/.env.example` there and set the InsForge
URL and anon key.

Start the frontend from `frontend/`:

```bash
npm install
npm run dev
```

### Project Layout

```text
backend/     FastAPI app, configuration, and placeholder service modules
frontend/    Next.js app, UI components, and API client
docs/        Project architecture notes
prompts/     Existing implementation prompts
```

## Goal

Build an AI-powered Kubernetes troubleshooting platform that can:

- Investigate Kubernetes failures
- Analyze logs, events, and cluster state
- Identify root causes
- Suggest fixes
- Store investigation history
- Be deployed publicly as a real application

---

# High Level Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                     │
│                                                            │
│  Pods | Deployments | Services | Events | Logs            │
│                                                            │
│  This is where failures happen and evidence exists         │
└────────────────────────────────────────────────────────────┘
                              │
                              │ kubectl / Kubernetes API
                              ▼
┌────────────────────────────────────────────────────────────┐
│                  Investigation Layer                      │
│                                                            │
│ Responsibility:                                            │
│ - Connect to Kubernetes cluster                            │
│ - Collect troubleshooting signals                          │
│ - Gather debugging evidence                                │
│                                                            │
│ Components:                                                │
│                                                            │
│  1. Pod Inspector                                          │
│     - Get pod health                                       │
│     - Detect CrashLoopBackOff                              │
│     - Detect Pending/Error states                          │
│                                                            │
│  2. Logs Collector                                         │
│     - Read pod logs                                        │
│     - Capture container errors                             │
│                                                            │
│  3. Events Analyzer                                        │
│     - Read Kubernetes events                               │
│     - Detect scheduling/image failures                     │
│                                                            │
│  4. Deployment Inspector                                   │
│     - Inspect deployment status                            │
│     - Verify rollout health                                │
│                                                            │
│  5. Network Inspector                                      │
│     - Check services                                       │
│     - Validate selectors                                   │
│     - Investigate DNS/networking issues                    │
└────────────────────────────────────────────────────────────┘
                              │
                              │ Structured Investigation Data
                              ▼
┌────────────────────────────────────────────────────────────┐
│                  AI Kubernetes Agent                      │
│                                                            │
│ Responsibility:                                            │
│ - Understand Kubernetes failures                           │
│ - Correlate logs + events + deployment state               │
│ - Identify root cause                                      │
│ - Recommend fixes                                          │
│                                                            │
│ Components:                                                │
│                                                            │
│  1. Prompt Builder                                         │
│     - Convert investigation data into LLM prompt           │
│                                                            │
│  2. LLM Reasoning Layer                                    │
│     - Uses OpenRouter API Key from InsForge                │
│     - Supports models like:                                │
│       - Claude                                              │
│       - GPT                                                 │
│       - DeepSeek                                            │
│                                                            │
│  3. Root Cause Analyzer                                    │
│     - Detect primary issue                                 │
│     - Correlate signals                                    │
│                                                            │
│  4. Fix Recommendation Engine                              │
│     - Suggest kubectl fixes                                │
│     - Recommend YAML updates                               │
│                                                            │
│  5. Confidence Scoring                                     │
│     - Confidence % for diagnosis                           │
└────────────────────────────────────────────────────────────┘
                              │
                              │ Investigation Result
                              ▼
┌────────────────────────────────────────────────────────────┐
│                    InsForge Backend                       │
│                                                            │
│ Responsibility:                                            │
│ - Authentication                                           │
│ - Backend APIs                                             │
│ - Investigation history                                    │
│ - Realtime investigation updates                           │
│                                                            │
│ Components:                                                │
│                                                            │
│  1. Authentication                                         │
│     - User login                                           │
│                                                            │
│  2. API Layer                                              │
│     - Trigger investigations                               │
│     - Return AI analysis                                   │
│                                                            │
│  3. Investigation History                                  │
│     - Store previous incidents                             │
│     - Save root cause reports                              │
│                                                            │
│  4. Realtime Updates                                       │
│     - Live investigation progress                          │
│                                                            │
│ Example:                                                    │
│  ✓ Checking pods                                           │
│  ✓ Reading logs                                            │
│  ✓ Analyzing events                                        │
│  ✓ Finding root cause                                      │
└────────────────────────────────────────────────────────────┘
                              │
                              │ API Response
                              ▼
┌────────────────────────────────────────────────────────────┐
│                     Frontend Dashboard                    │
│                                                            │
│ Responsibility:                                            │
│ - Trigger investigation                                    │
│ - Show realtime progress                                   │
│ - Display root cause                                       │
│ - Show suggested fixes                                     │
│ - Show investigation history                               │
│                                                            │
│ Example UI:                                                 │
│                                                            │
│ Incident: Payment Service Failure                          │
│                                                            │
│ Status: Investigating...                                   │
│                                                            │
│ ✓ Pods Checked                                             │
│ ✓ Events Analyzed                                          │
│ ✓ Logs Processed                                           │
│                                                            │
│ Root Cause: ImagePullBackOff                               │
│                                                            │
│ Suggested Fix:                                             │
│ Update invalid image tag                                   │
└────────────────────────────────────────────────────────────┘
                              │
                              │ Deploy Entire App
                              ▼
┌────────────────────────────────────────────────────────────┐
│                     InsForge Deployment                   │
│                                                            │
│ Responsibility:                                            │
│ - Deploy frontend                                          │
│ - Deploy backend                                           │
│ - Generate public URL                                      │
│                                                            │
│ Output:                                                     │
│                                                            │
│ https://ai-k8s-agent.public-url.app                        │
│                                                            │
│ Enables public access to the troubleshooting platform      │
└────────────────────────────────────────────────────────────┘
```

# End-to-End Workflow

```text
User clicks "Investigate Cluster"
                │
                ▼
Frontend sends API request
                │
                ▼
FastAPI Backend
      (Orchestration Layer)
                │
                ├── Authenticate User (InsForge)
                │
                ▼
Investigation Layer
                │
                ├── Check Pods
                ├── Read Logs
                ├── Analyze Events
                ├── Inspect Deployments
                └── Check Networking
                │
                ▼
AI Kubernetes Agent
                │
                ▼
LLM Reasoning
      (OpenRouter via InsForge Key)
                │
                ▼
Root Cause Analysis
                │
                ▼
Suggested Fix Generated
                │
                ├── Save Investigation History
                │        (InsForge)
                │
                ├── Realtime Progress Updates
                │        (InsForge)
                │
                ▼
Frontend Receives Result
                │
                ▼
User sees Diagnosis
```

# Example Failure Flow

```text
Issue:
Payment service unavailable

Agent Investigation:

✓ Pod Status Checked
✓ Logs Collected
✓ Events Analyzed

Detected Problem:
CrashLoopBackOff

Root Cause:
DATABASE_URL environment variable missing

Confidence:
94%

Suggested Fix:
Update deployment.yaml and add secret reference

Prevention:
Add startup validation checks
```

## Supported Kubernetes Problems

- CrashLoopBackOff
- ImagePullBackOff
- OOMKilled
- Pending Pods
- Resource Exhaustion
- Deployment Rollout Failures
- Service Selector Mismatch
- DNS Resolution Problems
- Readiness/Liveness Probe Failures
- Networking Issues

```
