# FinTrack - Personal Expense Management Platform

React + TypeScript frontend, an API gateway, six FastAPI microservices and MySQL.
This repository is the *application* half of a local DevSecOps learning project
(Docker, Jenkins, Trivy, Kubernetes, Helm, Prometheus, Grafana and Loki come next).

```
React (5173) -> API Gateway (8000) -> user 8001 | expense 8002 | category 8003
                                      budget 8004 | report 8005 | notification 8006 -> MySQL (3306)

Budget alerts:  expense-service --HTTP--> budget-service --HTTP--> notification-service
```

## Status

| Area | State |
|------|-------|
| MySQL schema, 6 services, gateway, JWT auth, ownership checks | working, API-tested |
| Budget alerts (80% warning / exceeded), de-duplicated | working, integration-tested |
| React frontend (11 pages) | working, builds; single large `App.tsx` still to be split into components |
| Playwright E2E specs | written; must be run on a machine with a browser |
| Report service: budget vs actual | working, API-tested |
| Docker and Compose | working, container and E2E-tested |
| Jenkins, Trivy, Kubernetes, Helm, monitoring, logging | **not started** |

## First-time setup

1. Create the database: `mysql -u root -p < database/init.sql`
2. Create each service's `.env` from its `.env.example` and set `DB_PASSWORD`
   (or let the script below create them and then edit `DB_PASSWORD`).
3. Generate ONE shared JWT secret for all services (services refuse to start without it):
   `python scripts/setup_env.py`
4. Install: `pip install -r backend/user-service/requirements.txt` (all services share the same packages),
   then `cd frontend/expense-ui && npm ci`.

## Run (each in its own terminal, from `backend/<service>`)

```
python -m uvicorn app.main:app --port 8001     # user-service; 8002 expense, 8003 category,
                                               # 8004 budget, 8005 report, 8006 notification,
                                               # 8000 api-gateway
cd frontend/expense-ui && npm run dev          # http://localhost:5173
```

## Tests

```
pytest tests                    # everything (needs MySQL running and init.sql loaded)
pytest tests/unit               # milliseconds, no database
pytest tests/api                # per-service API tests + gateway tests
pytest tests/integration        # expense -> budget -> notification chain
npm install && npx playwright install chromium && npm run e2e   # browser end-to-end (services + `npm run dev` running)
```

Tests create their own users and delete them afterwards, but they use the real `expense_tracker`
database - use a development database, never one with data you care about.

## Environment variables that connect services

| Variable | Set in | Meaning |
|----------|--------|---------|
| `JWT_SECRET` | every service | shared secret; >= 32 chars, not a placeholder |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | every DB service | where MySQL is |
| `BUDGET_SERVICE_URL` | expense-service | how expense finds budget |
| `NOTIFICATION_SERVICE_URL` | budget-service | how budget finds notification |
| `*_SERVICE_URL` | api-gateway | how the gateway finds every service |

`127.0.0.1` only works when everything runs on one machine. Inside Docker these become
service names (`http://budget-service:8004`) - the main networking lesson of the Docker phase.

## Docker architecture

FinTrack's Docker path is:

```
Source code -> Dockerfile -> Docker image -> Docker Compose -> Docker container -> Docker network
```

An image is the packaged, reusable filesystem for a component. A container is a running
instance of an image. A Dockerfile is the repeatable recipe used to build an image.
`docker-compose.yml` describes all nine components, their environment variables, dependencies,
health checks, ports, network, and storage so they can run together.

### Services and ports

| Compose service | Container port | Host access |
|---|---:|---:|
| `mysql` | 3306 | internal only |
| `user-service` | 8001 | internal only |
| `expense-service` | 8002 | internal only |
| `category-service` | 8003 | internal only |
| `budget-service` | 8004 | internal only |
| `report-service` | 8005 | internal only |
| `notification-service` | 8006 | internal only |
| `api-gateway` | 8000 | `http://localhost:8000` |
| `frontend` | 80 | `http://localhost:5173` |

The browser talks to the frontend, the frontend proxies `/api` to `api-gateway:8000`,
the gateway routes to the six microservices, and the database-backed services connect to
`mysql:3306`. The frontend never connects directly to MySQL.

Containers on the `personalexpensetracker_fintrack` Docker network use Compose service names
as DNS names. A container's `localhost` means that same container, so it cannot reach a
different service there. This is why Docker configuration uses names such as `mysql`,
`user-service`, `budget-service`, and `notification-service`, while the local non-Docker
setup can use `localhost` because all processes share the host machine.

A container port is the port used inside the container and on the private Docker network.
A host port publishes a service to the developer's machine; for example, host port `5173`
maps to the frontend's container port `80`. Backend ports remain private and are reached
through the gateway.

### Environment, health, and storage

Passwords and the shared `JWT_SECRET` are supplied through environment variables. They are
not stored in Dockerfiles or frontend code. `healthcheck` verifies that a process is ready,
and `depends_on` with `service_healthy` makes dependent services wait for their prerequisites.

MySQL stores its data in the named `mysql-data` volume. Containers can be recreated without
losing the database; do not use `docker compose down -v` unless you intentionally want to
delete that data.

Start the stack:

```
docker compose up -d --build
docker compose ps
```

Stop containers while preserving the volume:

```
docker compose down
```

The Compose network and volume are managed automatically. The repository also contains
`fintrack/*:local` image tags from individual image builds; the running Compose containers
currently use the `personalexpensetracker/*:latest` images.
