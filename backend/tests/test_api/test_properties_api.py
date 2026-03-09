"""API integration tests using in-memory SQLite."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# In-memory SQLite for tests
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)

SAMPLE_PROPERTY = {
    "name": "テスト塚口マンション",
    "source_url": "https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/nc_12345/",
    "address_text": "兵庫県尼崎市塚口本町1丁目",
    "station_name": "塚口",
    "walking_minutes": 5,
    "price_jpy": 35_000_000,
    "floor_area_sqm": 65.5,
    "layout": "3LDK",
    "built_year": 2015,
    "management_fee_jpy": 12_000,
    "repair_reserve_jpy": 10_000,
    "total_units": 48,
    "zoning_type": "近隣商業地域",
}


class TestPropertyCRUD:
    def test_create_property(self):
        res = client.post("/properties", json=SAMPLE_PROPERTY)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "テスト塚口マンション"
        assert data["price_jpy"] == 35_000_000

    def test_list_properties(self):
        client.post("/properties", json=SAMPLE_PROPERTY)
        res = client.get("/properties")
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_get_property(self):
        create_res = client.post("/properties", json=SAMPLE_PROPERTY)
        pid = create_res.json()["id"]
        res = client.get(f"/properties/{pid}")
        assert res.status_code == 200
        assert res.json()["id"] == pid

    def test_update_property(self):
        create_res = client.post("/properties", json=SAMPLE_PROPERTY)
        pid = create_res.json()["id"]
        res = client.patch(f"/properties/{pid}", json={"price_jpy": 32_000_000})
        assert res.status_code == 200
        assert res.json()["price_jpy"] == 32_000_000

    def test_delete_property(self):
        create_res = client.post("/properties", json=SAMPLE_PROPERTY)
        pid = create_res.json()["id"]
        res = client.delete(f"/properties/{pid}")
        assert res.status_code == 204
        assert client.get(f"/properties/{pid}").status_code == 404

    def test_get_not_found(self):
        res = client.get("/properties/999")
        assert res.status_code == 404


class TestLoanScenarios:
    def test_create_loan_scenario(self):
        prop = client.post("/properties", json=SAMPLE_PROPERTY).json()
        pid = prop["id"]
        loan_body = {
            "label": "変動金利0.5%",
            "down_payment_jpy": 7_000_000,
            "annual_interest_rate": 0.005,
            "loan_years": 35,
        }
        res = client.post(f"/properties/{pid}/loan-scenarios", json=loan_body)
        assert res.status_code == 201
        data = res.json()
        assert data["loan_amount_jpy"] == 28_000_000
        assert data["monthly_payment_jpy"] > 0

    def test_list_loan_scenarios(self):
        prop = client.post("/properties", json=SAMPLE_PROPERTY).json()
        pid = prop["id"]
        client.post(f"/properties/{pid}/loan-scenarios", json={
            "down_payment_jpy": 5_000_000,
            "annual_interest_rate": 0.005,
            "loan_years": 35,
        })
        client.post(f"/properties/{pid}/loan-scenarios", json={
            "down_payment_jpy": 10_000_000,
            "annual_interest_rate": 0.015,
            "loan_years": 35,
        })
        res = client.get(f"/properties/{pid}/loan-scenarios")
        assert res.status_code == 200
        assert len(res.json()) == 2


class TestRentalScenarios:
    def test_create_rental_scenario(self):
        prop = client.post("/properties", json=SAMPLE_PROPERTY).json()
        pid = prop["id"]
        # Create a loan first
        client.post(f"/properties/{pid}/loan-scenarios", json={
            "down_payment_jpy": 7_000_000,
            "annual_interest_rate": 0.005,
            "loan_years": 35,
        })
        rental_body = {
            "expected_rent_jpy": 120_000,
            "vacancy_rate": 0.05,
            "management_fee_rate": 0.05,
            "fixed_asset_tax_annual_jpy": 100_000,
        }
        res = client.post(f"/properties/{pid}/rental-scenarios", json=rental_body)
        assert res.status_code == 201
        data = res.json()
        assert data["monthly_net_cashflow_jpy"] is not None


class TestExitScore:
    def test_calculate(self):
        prop = client.post("/properties", json=SAMPLE_PROPERTY).json()
        pid = prop["id"]
        res = client.post(f"/properties/{pid}/exit-score/calculate")
        assert res.status_code == 201
        data = res.json()
        assert 0 <= data["total_score"] <= 100

    def test_get_latest(self):
        prop = client.post("/properties", json=SAMPLE_PROPERTY).json()
        pid = prop["id"]
        client.post(f"/properties/{pid}/exit-score/calculate")
        res = client.get(f"/properties/{pid}/exit-score")
        assert res.status_code == 200


class TestComparison:
    def test_compare_two(self):
        p1 = client.post("/properties", json=SAMPLE_PROPERTY).json()
        p2_data = {**SAMPLE_PROPERTY, "name": "物件B", "price_jpy": 28_000_000}
        p2 = client.post("/properties", json=p2_data).json()
        res = client.post("/comparison", json={"property_ids": [p1["id"], p2["id"]]})
        assert res.status_code == 200
        assert len(res.json()["properties"]) == 2


class TestHealth:
    def test_health(self):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
