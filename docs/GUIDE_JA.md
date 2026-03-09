# Home Decision OS 技術解説書

## この文書について

この文書は、Home Decision OS の設計・実装を**初心者にもわかるように**徹底的に解説したものです。

対象読者:
- Python を学習中の方
- Web API（FastAPI）を初めて扱う方
- Docker / PostgreSQL / CI/CD の実務経験がまだ浅い方
- ポートフォリオとしてこのプロジェクトを理解したい方

---

## 目次

1. プロジェクト全体像
2. ディレクトリ構成と役割
3. ドメインロジック（計算エンジン）
4. データベース設計（SQLAlchemy モデル）
5. API設計（FastAPI + Pydantic）
6. テスト戦略
7. Docker によるローカル環境構築
8. CI/CD（GitHub Actions）
9. 動作確認手順
10. よくあるエラーと対処法
11. フロントエンド（Next.js + TypeScript + Tailwind CSS）
12. 外部データ連携（コネクタ）
13. 次のステップ

---

## 1. プロジェクト全体像

### 何を作っているのか

住宅購入を検討している人が、**「この物件を買うべきかどうか」** をデータで判断できるツールです。

具体的には、物件を登録すると以下が自動計算されます:

- **住宅ローン月額** — 毎月いくら返済するか
- **所有コスト** — ローン + 管理費 + 修繕積立金 + 税金 + 保険の合計
- **将来賃貸キャッシュフロー** — 将来貸し出した場合、毎月いくら手元に残るか
- **出口スコア** — その物件が「貸しやすいか・売りやすいか」を0-100点で評価

### アーキテクチャ概念図

```
ユーザー（ブラウザ）
    │
    ▼
┌──────────────┐
│   Next.js    │  ← フロントエンド（Phase 3 で実装予定）
│   Frontend   │
└──────┬───────┘
       │ HTTP (JSON)
       ▼
┌──────────────┐
│   FastAPI    │  ← バックエンド REST API
│   Backend    │
├──────────────┤
│  Domain層    │  ← 計算ロジック（純粋なPython関数）
├──────────────┤
│  Repository層│  ← データベースアクセス
└──────┬───────┘
       │ SQL
       ▼
┌──────────────┐
│  PostgreSQL  │  ← データベース
└──────────────┘
```

### なぜこの構成なのか

| 設計判断 | 理由 |
|---------|------|
| FastAPI | 型安全なAPIを自動文書化（Swagger UI）。ポートフォリオ価値が高い |
| Domain層を分離 | 計算ロジックを API やDBに依存させない。テストしやすい |
| PostgreSQL | 本番運用にも耐える。SQL スキルを示せる |
| Docker Compose | 一コマンドで環境再現。面接官がすぐ試せる |

---

## 2. ディレクトリ構成と役割

```
home-decision-os/
├── backend/
│   ├── app/                        # アプリケーション本体
│   │   ├── api/
│   │   │   └── routes/             # ★ APIエンドポイント定義
│   │   │       ├── properties.py       物件 CRUD
│   │   │       ├── loan_scenarios.py   ローンシナリオ
│   │   │       ├── rental_scenarios.py 賃貸シナリオ
│   │   │       ├── exit_scores.py      出口スコア
│   │   │       └── comparison.py       物件比較
│   │   │
│   │   ├── domain/                 # ★ 計算ロジック（純粋関数）
│   │   │   ├── mortgage.py             住宅ローン計算
│   │   │   ├── ownership_cost.py       所有コスト計算
│   │   │   ├── rental_cashflow.py      賃貸CF計算
│   │   │   └── exit_score.py           出口スコア計算
│   │   │
│   │   ├── models/                 # ★ DB テーブル定義（SQLAlchemy ORM）
│   │   │   └── property.py
│   │   │
│   │   ├── schemas/                # ★ リクエスト/レスポンス型定義（Pydantic）
│   │   │   └── property.py
│   │   │
│   │   ├── repositories/           # ★ DB操作（CRUD）
│   │   │   └── property_repo.py
│   │   │
│   │   ├── services/               # ビジネスロジック統合（将来用）
│   │   ├── connectors/             # 外部データ連携（将来用）
│   │   ├── config.py               # 環境設定
│   │   ├── database.py             # DB接続管理
│   │   └── main.py                 # FastAPIアプリ起点
│   │
│   ├── tests/                      # テストコード
│   │   ├── test_domain/                計算ロジックのテスト
│   │   └── test_api/                   APIのテスト
│   │
│   ├── migrations/                 # Alembic DBマイグレーション
│   │   ├── env.py                      マイグレーション実行環境
│   │   └── versions/
│   │       └── 001_create_initial_tables.py
│   │
│   ├── scripts/
│   │   └── test_api_e2e.py         # E2Eテストスクリプト
│   │
│   ├── Dockerfile                  # Dockerイメージ定義
│   ├── requirements.txt            # Python依存パッケージ
│   ├── pyproject.toml              # プロジェクト設定
│   └── alembic.ini                 # Alembic設定
│
├── docker-compose.yml              # Docker Compose定義
├── .github/workflows/ci.yml        # GitHub Actions CI
└── README.md                       # プロジェクト説明
```

### 各層の役割（レイヤードアーキテクチャ）

```
API層（routes/）
  ↓ リクエストを受け取り、適切なサービスを呼ぶ
Domain層（domain/）
  ↓ 純粋な計算。DBもAPIも知らない
Repository層（repositories/）
  ↓ DBの読み書きだけに責任を持つ
Model層（models/）
  ↓ テーブル構造の定義
Database（PostgreSQL）
```

**なぜ層を分けるのか？**

たとえば `mortgage.py` の住宅ローン計算は、FastAPI がなくても、PostgreSQL がなくても動きます。
これにより:

- テストが簡単（DBなしで計算ロジックだけテストできる）
- 再利用しやすい（CLIツールやJupyter Notebookからも呼べる）
- 変更の影響範囲が限定的（DB変更してもドメインロジックは影響なし）

---

## 3. ドメインロジック（計算エンジン）

### 3.1 住宅ローン計算 — `domain/mortgage.py`

#### 元利均等返済とは

日本の住宅ローンで最も一般的な返済方式です。毎月の返済額（元本＋利息）が一定になります。

#### 計算式

```
M = P × r × (1+r)^n / ((1+r)^n - 1)
```

- `M`: 月々の返済額
- `P`: 借入額（元本）
- `r`: 月利（年利 ÷ 12）
- `n`: 総返済回数（年数 × 12）

#### コード解説

```python
def calc_monthly_payment(principal: int, annual_rate: float, years: int) -> int:
    """
    Parameters（引数）:
        principal   : 借入額（円）。例: 30,000,000（3000万円）
        annual_rate : 年利（小数）。例: 0.005（0.5%）
        years       : 返済年数。例: 35

    Returns（戻り値）:
        月々の返済額（円）。例: 77,875
    """
    if principal <= 0:
        return 0              # 借入なし → 返済なし
    if annual_rate <= 0:
        # 金利ゼロの場合: 単純に元本を回数で割る
        return -(-principal // (years * 12))  # 切り上げ除算のテクニック

    r = annual_rate / 12      # 年利 → 月利に変換
    n = years * 12            # 年数 → 月数に変換
    factor = (1 + r) ** n     # (1+r)^n を事前計算
    monthly = principal * r * factor / (factor - 1)
    return int(monthly + 0.5) # 四捨五入して整数に
```

**切り上げ除算のテクニック `--(-a // b)`:**
Python の `//` は切り捨て除算ですが、負の数に適用すると実質的に切り上げになります。
例: `-(-100 // 3)` → `-(-34)` → `34`（100÷3=33.33... の切り上げ）

#### 住宅ローン控除

2022年以降の新築は、年末残高の **0.7%** が所得税から控除されます（最大13年間）。

```python
def calc_tax_credit_annual(outstanding_balance: int, credit_rate: float = 0.007) -> int:
    """
    例: 残高3000万円 × 0.7% = 210,000円/年
    上限は21万円（一般的な新築の場合）
    """
    credit = int(outstanding_balance * credit_rate)
    return min(credit, 210_000)  # 上限超えたら上限値を返す
```

#### ローン残高の推計

```python
def approximate_outstanding_balance(principal, annual_rate, years, elapsed_years):
    """
    k年経過後の残高を求める標準公式:
    B_k = P × ((1+r)^n - (1+r)^k) / ((1+r)^n - 1)

    使い道: ローン控除額の年次計算、繰上返済シミュレーション
    """
```

### 3.2 所有コスト計算 — `domain/ownership_cost.py`

マンションを所有するには、ローン返済以外にも毎月かかるコストがあります。

```
月額所有コスト = ローン返済
              + 管理費        ← マンション共用部の清掃・管理
              + 修繕積立金    ← 将来の大規模修繕のための積立
              + 固定資産税/12 ← 毎年1月1日時点の所有者に課税
              + 保険/12       ← 火災保険・地震保険
              + その他/12     ← 町内会費など
```

```python
def calc_ownership_cost(
    monthly_loan_payment: int,  # 月額ローン返済
    management_fee: int,        # 管理費（月額）
    repair_reserve: int,        # 修繕積立金（月額）
    property_tax_annual: int,   # 固定資産税（年額） → /12 で月割り
    insurance_annual: int,      # 保険（年額） → /12 で月割り
    other_annual: int,          # その他（年額） → /12 で月割り
) -> OwnershipCostResult:
```

**ポイント:** 年額のものは `// 12` で月割りしています。Python の `//` は整数除算（切り捨て）です。

### 3.3 賃貸キャッシュフロー計算 — `domain/rental_cashflow.py`

将来この物件を人に貸した場合、毎月いくら手元に残るか（または持ち出しになるか）を計算します。

```
実効家賃 = 想定賃料 - 空室損失 - 管理委託費

  空室損失   = 想定賃料 × 空室率
  管理委託費 = 想定賃料 × 管理委託率

月次CF = 実効家賃 - 月額所有コスト
```

```python
def calc_rental_cashflow(
    expected_rent: int,             # 想定月額家賃。例: 120,000円
    vacancy_rate: float,            # 空室率。例: 0.05（5%）
    management_fee_rate: float,     # 管理委託率。例: 0.05（5%）
    ownership_cost_monthly: int,    # 月額所有コスト（前述の計算結果）
) -> RentalCashflowResult:
```

**空室率 5% の意味:** 年間で約3週間（365日 × 5% ≈ 18日）は空室になる想定です。
退去〜次の入居までの原状回復・募集期間を考慮した数字です。

**月次CFがプラス** → ローンを払いながらも手元にお金が残る（投資として成立）
**月次CFがマイナス** → ローン返済のほうが大きく、持ち出しが発生する

### 3.4 出口スコア計算 — `domain/exit_score.py`

物件を将来「貸しやすいか」「売りやすいか」を7つの要素で採点します。

| 要素 | 評価基準 | 高得点の条件 |
|------|---------|-------------|
| 駅距離 | 駅まで何分か | 5分以内 → 9-10点 |
| 面積 | 何㎡か | 60-75㎡ → 10点 |
| 間取り | 何LDKか | 2-3LDK → 10点 |
| 築年数 | 何年経っているか | 築10年以内 → 9-10点 |
| 用途地域 | どんなエリアか | 商業地域 → 9点 |
| ハザード | 災害リスク | リスクなし → 8点 |
| 総戸数 | マンション規模 | 50戸以上 → 8-9点 |

各要素 0-10点 × 7 = 最大70点 → 100点満点に正規化

```python
total = int(raw / 70 * 100 + 0.5)  # 70点満点 → 100点満点に変換
```

**なぜこの7要素なのか:**

日本の賃貸市場では「駅近・ファミリー向け・築浅」が最も需要が高く、
出口戦略（将来の賃貸・売却）の実現性を大きく左右します。
総戸数は修繕積立金の安定性の代理変数として使用しています。

---

## 4. データベース設計（SQLAlchemy モデル）

### 4.1 ER図（テーブル関連）

```
properties (物件)
    │
    ├── 1:N ──→ loan_scenarios (ローンシナリオ)
    │              同じ物件に対して「変動金利」「固定金利」など複数
    │
    ├── 1:N ──→ rental_scenarios (賃貸シナリオ)
    │              同じ物件に対して「楽観」「標準」「悲観」など複数
    │
    └── 1:N ──→ exit_scores (出口スコア)
                   物件情報が更新されるたびに再計算（履歴保持）
```

### 4.2 SQLAlchemy ORM とは

SQL を直接書く代わりに、Python のクラスでテーブルを定義し、
Python オブジェクトとしてデータを操作する仕組み（Object-Relational Mapping）です。

```python
# テーブル定義
class Property(Base):
    __tablename__ = "properties"   # 実際のテーブル名

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    price_jpy: Mapped[int] = mapped_column(Integer)
    # ...
```

これにより:
- `Property(name="テスト", price_jpy=3000)` でレコード作成
- `db.query(Property).filter(Property.id == 1).first()` でSELECT
- SQL を書かなくても型安全にDBを操作できる

### 4.3 リレーション（テーブル間の関連）

```python
class Property(Base):
    # 1つの物件 → 複数のローンシナリオ
    loan_scenarios: Mapped[list["LoanScenario"]] = relationship(
        back_populates="property",          # 逆方向のリレーション名
        cascade="all, delete-orphan"        # 物件削除時にシナリオも削除
    )

class LoanScenario(Base):
    # このシナリオがどの物件に属するか
    property_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("properties.id")         # 外部キー制約
    )
    property: Mapped["Property"] = relationship(back_populates="loan_scenarios")
```

**`cascade="all, delete-orphan"` の意味:**
親（Property）を削除すると、紐づく子（LoanScenario）も自動削除されます。
孤児（どの物件にも属さないシナリオ）も自動削除されます。

### 4.4 Alembic マイグレーション

DBスキーマ（テーブル構造）をバージョン管理する仕組みです。

```
alembic upgrade head    # 最新のスキーマに更新
alembic downgrade -1    # 1つ前の状態に戻す
alembic revision --autogenerate -m "add column"  # モデル変更を検知して自動生成
```

**なぜ必要か:** チーム開発や本番デプロイ時に「どのテーブルをいつ変更したか」を追跡するため。
`CREATE TABLE` を手動で実行するのではなく、コードとしてDB変更を管理します。

---

## 5. API設計（FastAPI + Pydantic）

### 5.1 REST API とは

HTTP メソッド（GET, POST, PATCH, DELETE）で操作を表現する Web API の設計パターンです。

| メソッド | 意味 | 例 |
|---------|------|------|
| `POST` | 新規作成 | `POST /properties` → 物件登録 |
| `GET` | 取得 | `GET /properties/1` → ID=1の物件取得 |
| `PATCH` | 部分更新 | `PATCH /properties/1` → 物件情報の一部を変更 |
| `DELETE` | 削除 | `DELETE /properties/1` → 物件削除 |

### 5.2 FastAPI エンドポイント解説

```python
# backend/app/api/routes/properties.py

router = APIRouter(prefix="/properties", tags=["properties"])
# prefix: このファイルの全URLの先頭に "/properties" がつく
# tags: Swagger UI でグループ分けするためのラベル


@router.post("", response_model=PropertyRead, status_code=201)
def create(body: PropertyCreate, db: Session = Depends(get_db)):
    """
    POST /properties にリクエストが来たとき実行される。

    body: PropertyCreate
        → リクエストボディのJSONを自動的にPydanticモデルに変換
        → バリデーション（型チェック、値の範囲チェック）も自動

    db: Session = Depends(get_db)
        → FastAPIの「依存性注入」機能
        → リクエストごとにDBセッションを生成し、終了後に閉じる

    response_model=PropertyRead
        → レスポンスのJSON形式を定義。不要なフィールドを除外

    status_code=201
        → 成功時のHTTPステータスコード（201 = Created）
    """
    prop = property_repo.create_property(db, **body.model_dump())
    return prop
```

**`Depends(get_db)` — 依存性注入（Dependency Injection）:**

```python
# database.py
def get_db():
    db = SessionLocal()   # DBセッション作成
    try:
        yield db          # エンドポイント関数に渡す
    finally:
        db.close()        # 必ずセッションを閉じる（リーク防止）
```

これにより、各APIエンドポイントはDB接続の管理を気にせず、
「DBセッションをもらって使う」だけで済みます。

### 5.3 Pydantic スキーマ

リクエスト/レスポンスの「型」を定義するクラスです。

```python
class PropertyCreate(BaseModel):
    """物件作成時のリクエストボディ"""
    name: str = Field(..., min_length=1, max_length=255)
    #   ...    : 必須フィールドを意味する
    #   min_length=1 : 空文字を許可しない
    #   max_length=255 : 255文字以内

    price_jpy: int = Field(..., gt=0)
    #   gt=0 : 0より大きい（greater than 0）

    walking_minutes: int | None = Field(None, ge=0)
    #   int | None : 整数 or null（省略可能）
    #   None : デフォルト値はnull
    #   ge=0 : 0以上（greater than or equal to 0）
```

**Create と Read を分ける理由:**

- `PropertyCreate` — ユーザーが**送る**データ（`id` や `created_at` は不要）
- `PropertyRead` — APIが**返す**データ（`id` や `created_at` を含む）

### 5.4 自動計算の流れ（ローンシナリオ作成の例）

```
ユーザーのリクエスト:
POST /properties/1/loan-scenarios
{
    "down_payment_jpy": 7000000,
    "annual_interest_rate": 0.005,
    "loan_years": 35
}

API の処理:
1. 物件を取得（price_jpy = 35,000,000）
2. ドメインロジックで計算:
   calc_mortgage(price=35M, down_payment=7M, rate=0.005, years=35)
   → loan_amount: 28,000,000
   → monthly_payment: 72,684
   → total_payment: 30,527,280
3. 計算結果をDBに保存
4. 結果を返す
```

**ポイント:** ユーザーは「頭金・金利・年数」だけ送ればよく、
月額返済額や総返済額はサーバー側で自動計算されます。

### 5.5 Swagger UI

FastAPI は API ドキュメントを自動生成します。

- `http://localhost:8000/docs` → Swagger UI（インタラクティブに試せる）
- `http://localhost:8000/redoc` → ReDoc（読みやすいドキュメント）

Swagger UI では:
1. エンドポイントを選ぶ
2. 「Try it out」をクリック
3. パラメータを入力
4. 「Execute」で実行
5. レスポンスが表示される

---

## 6. テスト戦略

### 6.1 テストの種類

| テスト種別 | 対象 | DB依存 | ファイル |
|-----------|------|--------|---------|
| ユニットテスト | 計算ロジック | なし | `test_domain/` |
| API統合テスト | エンドポイント | SQLite（メモリ内） | `test_api/` |
| E2Eテスト | 全体の動作 | PostgreSQL | `scripts/test_api_e2e.py` |

### 6.2 ドメインテストの例

```python
class TestCalcMonthlyPayment:
    def test_typical_loan(self):
        # 3000万円、年利0.5%、35年
        monthly = calc_monthly_payment(30_000_000, 0.005, 35)
        assert 77_000 <= monthly <= 78_000  # 約77,875円

    def test_zero_principal(self):
        # 借入0円 → 返済0円
        assert calc_monthly_payment(0, 0.01, 35) == 0
```

**`assert` 文:** 条件が False なら AssertionError でテスト失敗になります。
テストは「こう動くべき」という仕様書の役割も果たします。

### 6.3 API テストの仕組み

```python
# テスト用にSQLiteのメモリ内DBを使う（PostgreSQL不要）
engine = create_engine("sqlite://", poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)

# FastAPIのDB依存をテスト用に差し替え
app.dependency_overrides[get_db] = override_get_db
```

**なぜSQLiteを使うのか:**
- PostgreSQL を起動せずにテストできる
- テストが高速（メモリ内で完結）
- CIでもDB不要で実行可能

### 6.4 テスト実行方法

```bash
# ローカル実行（pip install ".[dev]" 済みの場合）
pytest -v --tb=short

# Docker 内で実行
docker compose exec api pytest -v --tb=short

# カバレッジ付き
pytest -v --cov=app --cov-report=term-missing
```

---

## 7. Docker によるローカル環境構築

### 7.1 Docker / Docker Compose とは

- **Docker**: アプリケーションを「コンテナ」という隔離された環境で動かす技術
- **Docker Compose**: 複数のコンテナ（DB + API など）をまとめて管理するツール

### 7.2 Dockerfile 解説

```dockerfile
FROM python:3.11-slim
# ベースイメージ: Python 3.11 の軽量版

WORKDIR /app
# コンテナ内の作業ディレクトリを /app に設定

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*
# PostgreSQL接続に必要なCライブラリをインストール
# psycopg2 のビルドに gcc と libpq-dev が必要

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# まず依存パッケージだけコピー・インストール
# → ソースコード変更時にキャッシュが効いてビルドが速い

COPY . .
# ソースコードをコンテナにコピー

ENV PYTHONPATH=/app
# Pythonが app/ モジュールを見つけられるようにパスを設定

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 7.3 docker-compose.yml 解説

```yaml
services:
  db:
    image: postgres:16-alpine              # PostgreSQL 16 の軽量イメージ
    environment:
      POSTGRES_USER: hdos                  # DBユーザー名
      POSTGRES_PASSWORD: hdos              # DBパスワード
      POSTGRES_DB: hdos                    # DB名
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hdos"]  # DB起動確認コマンド
      interval: 5s                         # 5秒ごとにチェック
      retries: 5                           # 5回リトライ

  api:
    build: ./backend                       # backend/ ディレクトリの Dockerfile を使用
    environment:
      HDOS_DATABASE_URL: postgresql://hdos:hdos@db:5432/hdos
      # ↑ "db" はDockerの内部DNS名（docker-compose のサービス名）
      # localhost ではない！
      PYTHONPATH: /app
    depends_on:
      db:
        condition: service_healthy         # DBのヘルスチェックが通るまで待つ
    command: >
      sh -c "alembic upgrade head &&       # ① まずDBマイグレーション実行
             uvicorn app.main:app          # ② それからAPIサーバー起動
             --host 0.0.0.0 --port 8000 --reload"
```

**重要: `db` ホスト名**

Docker Compose 内では、各サービスは**サービス名**でお互いに通信できます。
`api` コンテナから `db` コンテナへの接続先は `localhost` ではなく `db` です。
（各コンテナは独立したネットワーク空間を持つため）

### 7.4 よく使うコマンド

```bash
docker compose up --build       # ビルドして起動（初回/変更後）
docker compose up               # 起動のみ（ビルド済みの場合）
docker compose down             # 停止・コンテナ削除
docker compose logs api         # APIコンテナのログ表示
docker compose exec api bash    # APIコンテナ内でシェルを起動
docker compose ps               # 実行中のコンテナ一覧
```

---

## 8. CI/CD（GitHub Actions）

### 8.1 CIとは

Continuous Integration（継続的インテグレーション）。
コードを push するたびに自動でテスト・lintを実行し、品質を保証する仕組みです。

### 8.2 ワークフロー解説

```yaml
# .github/workflows/ci.yml

name: CI
on:
  push:
    branches: [main]         # main ブランチへの push で実行
  pull_request:
    branches: [main]         # main への PR でも実行

jobs:
  lint-and-test:
    runs-on: ubuntu-latest   # GitHub が提供する Ubuntu マシン上で実行
    defaults:
      run:
        working-directory: backend  # 全コマンドを backend/ で実行

    steps:
      - uses: actions/checkout@v4        # リポジトリのコードを取得
      - uses: actions/setup-python@v5    # Python 3.11 をインストール
        with:
          python-version: "3.11"

      - run: pip install ".[dev]"        # 依存パッケージをインストール
      - run: ruff check .               # lint: コードスタイルチェック
      - run: ruff format --check .       # format: フォーマットチェック
      - run: pytest -v --tb=short --cov=app  # テスト実行 + カバレッジ
```

### 8.3 ruff とは

Python の高速リンター/フォーマッター。以下をチェックします:

- `E`: PEP 8 スタイル違反（インデント、空白）
- `F`: 未使用の import、未定義変数
- `I`: import の並び順
- `N`: 命名規約（クラスはCamelCase、変数はsnake_case）
- `W`: 警告（末尾空白など）
- `UP`: Python バージョンアップグレード提案

---

## 9. 動作確認手順

### 9.1 起動

```bash
docker compose up --build
```

### 9.2 テストスクリプト実行

別のターミナルで:

```bash
docker compose exec api python scripts/test_api_e2e.py
```

このスクリプトは以下を自動実行します:

1. ヘルスチェック
2. 塚口エリアのマンション3件を登録
   - プラウド塚口（3800万円・駅3分・築8年）
   - ルネ塚口（2800万円・駅7分・築21年）
   - グランドメゾン塚口（2200万円・駅12分・築28年）
3. 各物件に2つのローンシナリオを作成
   - 変動金利 0.5% / 頭金10%
   - 固定金利 1.5% / 頭金20%
4. 各物件に賃貸シナリオを作成
5. 出口スコアを計算
6. 3物件を横並び比較

### 9.3 Swagger UI で手動確認

ブラウザで `http://localhost:8000/docs` を開き:

1. `POST /properties` で物件登録
2. `POST /properties/{id}/loan-scenarios` でローン計算
3. `POST /properties/{id}/rental-scenarios` で賃貸CF計算
4. `POST /properties/{id}/exit-score/calculate` で出口スコア計算
5. `POST /comparison` で物件比較

### 9.4 pytest 実行

```bash
docker compose exec api pip install httpx pytest pytest-cov
docker compose exec api pytest -v --tb=short
```

---

## 10. よくあるエラーと対処法

### `ModuleNotFoundError: No module named 'app'`

**原因:** PYTHONPATH が設定されていない
**対処:** Dockerfile に `ENV PYTHONPATH=/app` があるか確認。
docker-compose.yml の environment にも `PYTHONPATH: /app` を追加。

### `connection to server at "localhost" ... refused`

**原因:** Docker 内で `localhost` に接続しようとしている
**対処:** Docker Compose では DB のホスト名は `db`（サービス名）。
`HDOS_DATABASE_URL` が `postgresql://hdos:hdos@db:5432/hdos` になっているか確認。

### `alembic: No module named 'app'`

**原因:** Alembic 実行時に Python パスが通っていない
**対処:** `migrations/env.py` で `from app.database import Base` が動くよう、
PYTHONPATH が設定されているか確認。

### `relation "properties" does not exist`

**原因:** マイグレーションが未実行
**対処:** `docker compose exec api alembic upgrade head` を実行

### Docker Desktop 起動エラー（Windows）

**原因:** Docker Desktop が起動していない
**対処:** タスクバー右下のシステムトレイにクジラアイコンが出るまで待つ。
WSL2 が必要な場合は `wsl --update` を実行。

---

## 11. フロントエンド（Next.js + TypeScript + Tailwind CSS）

### 11.1 技術選定

| 技術 | 役割 | 選定理由 |
|------|------|---------|
| Next.js 14 | React フレームワーク | App Router・SSR/SSG対応。転職市場で高評価 |
| TypeScript | 型安全な JavaScript | バグの早期発見。IDEの補完が強力 |
| Tailwind CSS | ユーティリティCSS | クラス名だけでデザイン完結。CSS ファイル管理不要 |
| Recharts | チャートライブラリ | React と相性が良い（将来のグラフ表示用） |

### 11.2 ディレクトリ構成

```
frontend/
├── app/                    # Next.js App Router
│   ├── layout.tsx             ルートレイアウト（ナビゲーション）
│   ├── page.tsx               物件一覧（ホーム）
│   ├── globals.css            Tailwind ベーススタイル
│   ├── properties/
│   │   ├── new/page.tsx       物件登録フォーム
│   │   └── [id]/page.tsx      物件詳細（ローン・賃貸・出口スコア）
│   └── comparison/
│       └── page.tsx           比較ダッシュボード
├── components/             # 再利用可能なUIコンポーネント
│   ├── PropertyCard.tsx       物件カード
│   ├── KpiCard.tsx            KPI表示カード
│   └── ScoreBar.tsx           スコアバー（プログレスバー）
├── lib/                    # ロジック・ユーティリティ
│   ├── api.ts                 API クライアント
│   ├── types.ts               TypeScript 型定義
│   └── format.ts              日本円フォーマッタ
└── Dockerfile
```

### 11.3 App Router とは

Next.js 13+ で導入された新しいルーティング方式です。
**フォルダ構造 = URL構造** になっています:

```
app/page.tsx                  → /
app/properties/new/page.tsx   → /properties/new
app/properties/[id]/page.tsx  → /properties/1, /properties/2, ...
app/comparison/page.tsx       → /comparison
```

`[id]` は「動的ルート」で、URLのその部分を変数として受け取ります:

```typescript
const { id } = useParams();  // URL が /properties/3 なら id = "3"
```

### 11.4 APIクライアント — `lib/api.ts`

バックエンドとの通信を一元管理する関数群です。

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}
```

**ジェネリクス `<T>`:** 戻り値の型をコール側で指定できます。
`request<Property[]>("/properties")` → 戻り値は `Property[]` 型

**`process.env.NEXT_PUBLIC_API_URL`:**
`NEXT_PUBLIC_` プレフィックスがついた環境変数はブラウザに露出します。
Docker Compose では `http://localhost:8000` を設定しています。

### 11.5 コンポーネント設計の考え方

**"use client" ディレクティブ:**

```typescript
"use client";  // ← このファイルはブラウザ側で実行される
```

Next.js のApp Router ではデフォルトで Server Component（サーバー側で実行）ですが、
`useState`, `useEffect` などのフック（状態管理・副作用）を使う場合は
`"use client"` を宣言して Client Component にします。

**フォームのパターン:**

```typescript
const [form, setForm] = useState<PropertyCreate>(INITIAL);

// 特定のフィールドだけを更新するヘルパー
function set<K extends keyof PropertyCreate>(key: K, value: PropertyCreate[K]) {
  setForm((prev) => ({ ...prev, [key]: value }));
}
```

`...prev` は「スプレッド構文」で、オブジェクトの全フィールドをコピーし、
`[key]: value` で指定したフィールドだけを上書きします。

### 11.6 Tailwind CSS の読み方

```html
<div className="bg-white rounded-lg border border-gray-200 p-4">
```

| クラス | 意味 |
|--------|------|
| `bg-white` | 背景: 白 |
| `rounded-lg` | 角丸: 大きめ |
| `border` | ボーダー: 1px |
| `border-gray-200` | ボーダー色: 薄いグレー |
| `p-4` | パディング: 1rem（16px） |

レスポンシブ対応は `sm:`, `md:`, `lg:` プレフィックス:
```html
<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
```
- デフォルト: 1列
- 640px以上(`sm`): 2列
- 1024px以上(`lg`): 3列

### 11.7 画面構成

| 画面 | URL | 機能 |
|------|-----|------|
| 物件一覧 | `/` | 登録済み物件のカード一覧表示 |
| 物件登録 | `/properties/new` | フォームから新規物件登録 |
| 物件詳細 | `/properties/{id}` | ローン・賃貸シナリオ追加、出口スコア計算 |
| 比較 | `/comparison` | 複数物件の横並び比較テーブル |

---

## 12. 外部データ連携（コネクタ）

Phase 4 として、外部データソースとの連携機能（コネクタ）を実装しました。
コネクタは「**外部からデータを取得して統一的な形式で返す**」部品です。

### 12.1 コネクタの設計思想

```
backend/app/connectors/
├── base.py              # 基底クラス（全コネクタ共通のインターフェース）
├── url_preview.py       # URL メタデータ取得
├── rent_estimator.py    # 賃料推定エンジン
└── mlit_transaction.py  # 国交省 不動産取引API
```

すべてのコネクタは `BaseConnector` を継承し、`ConnectorResult` を返します。

```python
@dataclass
class ConnectorResult:
    success: bool           # 成功/失敗
    source: str             # コネクタ名
    data: dict[str, Any]    # 取得データ
    errors: list[str]       # エラーメッセージ
```

この設計のメリット:
- **統一インターフェース**: 呼び出し側は `result.success` をチェックするだけ
- **テスト容易性**: コネクタを差し替えてモック化しやすい
- **拡張性**: 新しいデータソース追加時、BaseConnector を継承するだけ

### 12.2 URL プレビュー（OGP メタデータ取得）

不動産ポータルサイト（SUUMO、LIFULL HOME'S など）の URL を貼ると、物件情報を自動取得する機能です。

仕組み:
1. 指定 URL の HTML を `httpx` で取得
2. `<meta property="og:title">` などの OGP タグを正規表現で抽出
3. SUUMO の URL の場合、タイトルと説明文から追加情報をパース

```python
# SUUMO タイトルの例: "プラウド塚口 3LDK 65.5㎡ 3,500万円"
# 正規表現で以下を抽出:
m = re.search(r"([\d,]+)\s*万円", combined)  # → 3,500 → 35,000,000円
m = re.search(r"([\d.]+)\s*[㎡m²]", combined)  # → 65.5㎡
m = re.search(r"\b(\d[LDKS]{1,4})\b", combined)  # → 3LDK
m = re.search(r"徒歩\s*(\d+)\s*分", combined)  # → 5分
m = re.search(r"「?([^」\s]{2,6})駅」?", combined)  # → 塚口
```

フロントエンドでは、物件登録フォームに URL を貼って「自動取得」ボタンを押すと、
空欄のフィールドに自動入力されます（既に入力済みのフィールドは上書きしません）。

### 12.3 賃料推定エンジン

物件を将来賃貸に出した場合の想定家賃を、以下のロジックで推定します。

```
推定月額家賃 = 物件価格 × 調整済み利回り ÷ 12
```

**利回りテーブル（都道府県別）**:

| 都道府県 | 表面利回り |
|----------|-----------|
| 東京都 | 4.2% |
| 大阪府 | 5.0% |
| 兵庫県 | 5.5% |
| 神奈川県 | 4.8% |
| その他 | 5.5% |

利回りは以下の要因で調整されます:

**築年数による割引**（古いほど家賃が下がる）:
- 築0-5年: 100%（割引なし）
- 築11-15年: 93%
- 築21-25年: 82%
- 築31年以上: 68%

**駅距離によるプレミアム**:
- 徒歩3分以内: +5%
- 徒歩5分以内: +2%
- 徒歩11-15分: -7%
- 徒歩16分以上: -12%

計算例（プラウド塚口 3,800万円、築11年、徒歩5分、兵庫県）:

```
基本利回り: 5.5%
× 築年数係数: 0.93（築11年）
× 駅距離係数: 1.02（徒歩5分）
= 調整済み利回り: 5.22%

月額家賃 = 38,000,000 × 5.22% ÷ 12 ≒ 165,000円
信頼区間: 140,000円 〜 190,000円（±15%）
```

### 12.4 国交省 不動産取引API（MLIT）

国土交通省の「不動産情報ライブラリ」から実際の取引価格データを取得します。
このAPIは無料で利用できますが、API キーの取得が必要です。

取得URL: `https://www.reinfolib.mlit.go.jp/`

```python
# 設定方法（.env ファイルまたは環境変数）
HDOS_MLIT_API_KEY=your-api-key-here
```

レスポンスには地域の取引統計（中央値、平均単価、取引件数）が含まれ、
賃料推定のクロスバリデーションに活用されます。

### 12.5 コネクタ API エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/connectors/url-preview` | URL からメタデータ取得 |
| POST | `/connectors/market-data` | 不動産取引データ取得（要APIキー）|
| POST | `/connectors/rent-estimate` | 賃料推定 |

### 12.6 フロントエンドとの連携

**物件登録フォーム**:
URL 入力欄の横に「自動取得」ボタンを配置。クリックすると `fetchURLPreview(url)` を呼び、
取得したデータで空欄フィールドを自動入力します。

```typescript
// frontend/lib/api.ts
export async function fetchURLPreview(url: string): Promise<URLPreviewResponse> {
  return request("/connectors/url-preview", { method: "POST", body: JSON.stringify({ url }) });
}
```

**物件詳細ページ**:
「賃料を推定」ボタンで `fetchRentEstimate(params)` を呼び、
推定家賃・信頼区間・利回りを表示します。
この値をそのまま賃貸シナリオの想定家賃に使用できます。

### 12.7 コネクタのテスト

コネクタのテストは **外部通信なしで動作する** ように設計しています。

- `test_url_preview.py`: HTML パースロジック（`_extract_meta`, `_parse_suumo_hints`）のみテスト。HTTPは呼ばない。
- `test_rent_estimator.py`: `RentEstimatorConnector.fetch()` を直接呼び出し。外部APIは不使用。

テスト実行:
```bash
docker compose exec api pytest tests/test_domain/test_url_preview.py tests/test_domain/test_rent_estimator.py -v
```

---

## 13. 次のステップ

### Phase 5: AWS デプロイ
- AWS App Runner（API）
- AWS RDS（PostgreSQL）
- GitHub Actions → AWS 自動デプロイ
- カスタムドメイン設定

### Phase 6: 発展的な機能
- e-Stat（統計データ）連携
- ハザードマップ情報の自動判定
- ML ベースの賃料推定モデル
- 物件スコアリングの重み付けカスタマイズ

---

## 付録: 主要な Python 構文解説

### 型ヒント

```python
def calc(principal: int, rate: float) -> int:
    # principal は int 型、rate は float 型、戻り値は int 型
```

型ヒントは実行時には強制されませんが、IDE の補完やエラー検出に役立ちます。

### dataclass

```python
@dataclass(frozen=True)
class MortgageResult:
    monthly_payment: int
    total_payment: int
```

`@dataclass` は `__init__` や `__repr__` を自動生成するデコレータです。
`frozen=True` はイミュータブル（変更不可）にします。
→ 計算結果を「変更されない値の塊」として扱うのに適しています。

### `**kwargs` と `model_dump()`

```python
prop = property_repo.create_property(db, **body.model_dump())
```

- `body.model_dump()` → Pydantic モデルを辞書に変換 `{"name": "テスト", "price_jpy": 3000}`
- `**` → 辞書を展開してキーワード引数として渡す: `create_property(db, name="テスト", price_jpy=3000)`

### `|` 演算子（型の Union）

```python
walking_minutes: int | None
```

Python 3.10+ の構文。`int` または `None`（未設定）を許容します。
旧い書き方では `Optional[int]` や `Union[int, None]` です。

---

*この文書は Home Decision OS v0.1.0 に基づいています。*
