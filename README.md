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
                   ┌──────┴───────┐     ┌─────────────┐
                   │   Domain     │     │ Connectors  │
                   │  ┌─────────┐ │     │ ┌─────────┐ │
                   │  │Mortgage │ │     │ │URL Prev │ │
                   │  │OwnerCF  │ │     │ │Rent Est │ │
                   │  │RentalCF │ │     │ │MLIT API │ │
                   │  │ExitScore│ │     │ └─────────┘ │
                   │  └─────────┘ │     └─────────────┘
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
| `POST`   | `/connectors/url-preview` | Extract metadata from property listing URL |
| `POST`   | `/connectors/market-data` | Fetch MLIT transaction data (requires API key) |
| `POST`   | `/connectors/rent-estimate` | Estimate monthly rent for a property |
| `POST`   | `/connectors/alerts/tsukaguchi/run` | Run the 塚口 new-listing alert and push matches to LINE |

Interactive API docs available at `http://localhost:8000/docs` (Swagger UI).

## 塚口エリア 新着物件アラート (LINE通知)

塚口エリアの**中古マンション・中古戸建て**の新着を定期巡回し、徒歩条件を満たす物件が
出たら **LINE** に通知します。

### 通知条件

物件が次の条件を **すべて** 満たすと通知対象になります:

1. **徒歩条件**（`tsukaguchi_filter.py`）— 次のいずれか:
   - **阪急塚口** 徒歩 **10分以内**、または
   - **阪急塚口・JR塚口 の両方** が徒歩 **15分以内**
2. **間取り**: **3LDK 以上**（部屋数3以上。`HDOS_ALERT_MIN_ROOMS` / `--min-rooms` で変更可）

> SUUMO / HOME'S の検索カードは最寄り路線しか表示しないことが多いため、
> 路線名が不明な「塚口」徒歩10分以内は阪急塚口とみなして通知します
> （取りこぼし回避。`assume_unknown_is_hankyu=false` で無効化可）。
> athome は各物件の全路線アクセスを取得するため、ルール (B) も判定できます。

### セットアップ

1. **LINE Messaging API チャネル**を作成（LINE公式アカウント）。
   ※ LINE Notify は 2025-03-31 に終了したため Messaging API を使用します。
2. 次の環境変数（GitHub Actions では Secrets）を設定:

   | 変数 | 用途 |
   |------|------|
   | `HDOS_LINE_CHANNEL_TOKEN` | チャネルアクセストークン（必須） |
   | `HDOS_LINE_TARGET_ID` | 通知先 userId/groupId/roomId（空ならブロードキャスト） |
   | `HDOS_ALERT_STATE_PATH` | 既読リストの保存先（既定: `.alert_state/tsukaguchi_seen.json`） |
   | `HDOS_ALERT_MIN_ROOMS` | 最低部屋数（既定 3 = 3LDK以上） |
   | `HDOS_ALERT_USE_BROWSER` | ブラウザ取得の ON/OFF（既定 true） |
   | `HDOS_SCRAPE_PROXY` | 任意。アンチボット回避用プロキシ（後述） |

3. 定期実行は GitHub Actions ワークフローで行います（3時間ごと / 手動実行可）。
   `docs/tsukaguchi-alert.workflow.yml` を `.github/workflows/tsukaguchi-alert.yml`
   にコピーして有効化してください
   （自動コミットでは `workflows` 権限の都合で `.github/workflows` 配下に
   直接置けないため `docs/` に同梱しています）。
   既読状態は `actions/cache` で実行間に保持され、新着のみが通知されます。

### データ取得について

- **SUUMO / HOME'S** — 通常の HTTP 取得（httpx）でライブ動作を確認済み
  （尼崎市の中古マンション/戸建て一覧 → 塚口徒歩条件でフィルタ）。
- **athome** — Angular アプリで、物件データは SSR の TransferState JSON
  （`data.bukkenData.bukkenList`）として埋め込まれています。これを解析するため
  httpx だけで取得できます。athome はアクセス全路線を持つので、複数路線の判定にも
  対応します。なお athome は Imperva 系のボット保護（「認証中」ページ）があるため、
  **トップページを先に叩いて認証 Cookie を取得**してから一覧を取得します。
- `use_browser`（既定 ON）は **HTTP を先に試し、応答が空/ボット保護ページの場合だけ**
  ヘッドレスブラウザ（Playwright）で再取得します（JS チャレンジを通過）。
  Playwright 未導入時は自動的に無効化されます
  （`HDOS_ALERT_USE_BROWSER=false` / `--no-browser` で無効化）。

> **アンチボットと IP について（重要）:** SUUMO / athome はデータセンター IP
> （GitHub Actions の Azure IP 等）を弾くことがあります。Cookie ウォームアップと
> ブラウザフォールバックで多くは通過できますが、IP のレピュテーション次第で
> ブロックされる場合があります。確実性が必要なら次のいずれかを推奨します:
> 1. `HDOS_SCRAPE_PROXY=http://user:pass@host:port` に **住宅用プロキシ**を設定
> 2. ワークフローではなく **自宅などの回線（住宅 IP）で cron 実行**
>
> ルール (B)「阪急・JR 両塚口とも徒歩15分」は、最寄り1路線しか出さない
> SUUMO/HOME'S カードでは判定しきれない場合があります（athome は全路線を持つため
> 判定可能）。

### 手動実行 / 動作確認

```bash
cd backend
# 送信せず対象物件だけ確認（既読状態は更新されます）
python scripts/run_tsukaguchi_alert.py --dry-run
# 実際に LINE 通知
python scripts/run_tsukaguchi_alert.py
```

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
- [x] New-listing alert with LINE notification (塚口エリア)
- Alert system for price changes

## Design Intent

This project demonstrates the ability to:
- **Structure a real-world problem** into a data model and product
- **Build a full-stack application** with Python / SQL / REST API / Docker
- **Apply domain knowledge** (Japanese real estate, mortgage math, investment analysis)
- **Think in products** — not just code, but user value

---

Built by Kazuya Koga
