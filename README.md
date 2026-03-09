# Home Decision OS

**住宅購入の意思決定エンジン** — Housing Purchase Decision Engine for the Japanese Market

## Background

Home buyers in Japan face fragmented information across multiple services: property portals (SUUMO, LIFULL HOME'S), bank loan simulators, hazard maps, and rental market data. There is no single tool that lets you quantitatively evaluate **"Should I buy this property?"** considering mortgage costs, ownership expenses, future rental potential, and exit strategy — all in one place.

Home Decision OS consolidates these analyses into a single product.

## What It Does

Given a property and your financial assumptions, the system calculates:

1. **Mortgage simulation** — monthly/annual/total payments (元利均等返済)
2. **Ownership cost** — loan + management fee + repair reserve + tax + insurance
3. **Rental cashflow** — projected monthly CF if you rent the property out in the future
4. **Exit score** — rule-based 0-100 score evaluating rent-ability and sell-ability
5. **Side-by-side comparison** of multiple properties and scenarios

## Architecture

```
┌────────────┐     ┌──────────────┐     ┌────────────┐
│  Next.js   │────▶│   FastAPI    │────▶│ PostgreSQL │
│  Frontend  │◀────│   REST API   │◀────│    DB      │
└────────────┘     └──────┬───────┘     └────────────┘
                          │
                   ┌──────┴───────┐
                   │   Domain     │
                   │  ┌─────────┐ │
                   │  │Mortgage │ │
                   │  │OwnerCF  │ │
                   │  │RentalCF │ │
                   │  │ExitScore│ │
                   │  └─────────┘ │
                   └──────────────┘
```

## Tech Stack

| Layer        | Technology                          |
|-------------|-------------------------------------|
| Frontend    | Next.js · TypeScript · Tailwind CSS |
| Backend     | Python 3.11 · FastAPI · Pydantic    |
| Database    | PostgreSQL 16 · SQLAlchemy · Alembic |
| DevOps      | Docker Compose · GitHub Actions     |
| Infra (planned) | AWS App Runner · RDS · S3      |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST`   | `/properties` | Register a property |
| `GET`    | `/properties` | List all properties |
| `GET`    | `/properties/{id}` | Get property detail |
| `PATCH`  | `/properties/{id}` | Update property |
| `DELETE`  | `/properties/{id}` | Delete property |
| `POST`   | `/properties/{id}/loan-scenarios` | Create loan scenario (auto-calculates) |
| `GET`    | `/properties/{id}/loan-scenarios` | List loan scenarios |
| `POST`   | `/properties/{id}/rental-scenarios` | Create rental scenario (auto-calculates CF) |
| `GET`    | `/properties/{id}/rental-scenarios` | List rental scenarios |
| `POST`   | `/properties/{id}/exit-score/calculate` | Calculate exit score |
| `GET`    | `/properties/{id}/exit-score` | Get latest exit score |
| `POST`   | `/comparison` | Compare multiple properties side-by-side |

Interactive API docs available at `http://localhost:8000/docs` (Swagger UI).

## DB Schema

```
properties ──┬── loan_scenarios
             ├── rental_scenarios
             └── exit_scores
```

Key design decisions:
- One property can have **multiple loan scenarios** (variable vs fixed rate, different down payments)
- One property can have **multiple rental scenarios** (optimistic / standard / pessimistic rent)
- Exit scores are **append-only** (recalculated as property data changes)

## Calculation Logic

### Mortgage (元利均等返済)
Standard amortisation formula: `M = P × r(1+r)^n / ((1+r)^n − 1)`

### Ownership Cost
`Monthly = Loan Payment + Management Fee + Repair Reserve + Tax/12 + Insurance/12`

### Rental Cashflow
`Effective Rent = Rent × (1 − Vacancy Rate) − Management Commission`
`Monthly CF = Effective Rent − Ownership Cost`

### Exit Score (0-100)
Rule-based scoring across 7 factors: station proximity, floor area, layout, building age, zoning, hazard risk, and building size (liquidity proxy).

## Quick Start

```bash
# Clone and start
git clone https://github.com/your-username/home-decision-os.git
cd home-decision-os
docker compose up --build

# API is available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### Run Tests

```bash
cd backend
pip install ".[dev]"
pytest -v
```

### Lint

```bash
ruff check backend/
ruff format --check backend/
```

## Project Structure

```
home-decision-os/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI route handlers
│   │   ├── domain/           # Pure calculation logic
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── repositories/     # DB access layer
│   │   ├── services/         # Business logic orchestration
│   │   ├── connectors/       # External data connectors (future)
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   ├── tests/
│   ├── migrations/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── app/                   # Next.js App Router pages
│   │   ├── page.tsx               Property list (home)
│   │   ├── properties/new/        Property registration form
│   │   ├── properties/[id]/       Property detail + scenarios
│   │   └── comparison/            Side-by-side comparison
│   ├── components/            # Reusable UI components
│   ├── lib/                   # API client, types, formatters
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Development Phases

- [x] **Phase 0** — Requirements & design
- [x] **Phase 1** — Calculation logic + tests
- [x] **Phase 2** — FastAPI + PostgreSQL + migrations
- [x] **Phase 3** — Next.js UI
- [ ] **Phase 4** — Public data integration (不動産情報ライブラリ, e-Stat)
- [ ] **Phase 5** — Docker + CI/CD + AWS deploy

## Future Roadmap

- URL parser connector for SUUMO / LIFULL HOME'S
- Automated area data enrichment from public APIs
- Rent estimation model (ML-based)
- Future resale price estimation
- User authentication and multi-tenancy
- Alert system for price changes

## Design Intent

This project demonstrates the ability to:
- **Structure a real-world problem** into a data model and product
- **Build a full-stack application** with Python / SQL / REST API / Docker
- **Apply domain knowledge** (Japanese real estate, mortgage math, investment analysis)
- **Think in products** — not just code, but user value

---

Built by Kazuya Koga
