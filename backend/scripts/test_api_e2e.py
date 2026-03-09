#!/usr/bin/env python3
"""End-to-end API test script.

塚口エリアのマンション3件を登録し、ローン・賃貸・出口スコアを計算、
最後に比較APIで横並び比較を行う。

Usage (Docker内で実行):
    docker compose exec api python scripts/test_api_e2e.py

Usage (ローカルで実行):
    python scripts/test_api_e2e.py
"""

import json
import sys

import httpx

BASE = "http://localhost:8000"
client = httpx.Client(base_url=BASE, timeout=10)


def pp(label: str, data: dict | list) -> None:
    """Pretty-print API response."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------
r = client.get("/health")
assert r.status_code == 200, f"Health check failed: {r.text}"
print("✓ Health check OK")


# ---------------------------------------------------------------
# 2. Register 3 properties (塚口エリア)
# ---------------------------------------------------------------
properties_data = [
    {
        "name": "プラウド塚口",
        "source_url": "https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/nc_00001/",
        "address_text": "兵庫県尼崎市塚口本町1丁目",
        "station_name": "塚口",
        "walking_minutes": 3,
        "price_jpy": 38_000_000,
        "floor_area_sqm": 68.5,
        "layout": "3LDK",
        "built_year": 2018,
        "management_fee_jpy": 12_500,
        "repair_reserve_jpy": 9_800,
        "floor_number": 5,
        "total_floors": 10,
        "total_units": 52,
        "zoning_type": "近隣商業地域",
        "hazard_flag": False,
        "memo": "駅近・築浅・管理体制良好",
    },
    {
        "name": "ルネ塚口",
        "source_url": "https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/nc_00002/",
        "address_text": "兵庫県尼崎市南塚口町2丁目",
        "station_name": "塚口",
        "walking_minutes": 7,
        "price_jpy": 28_000_000,
        "floor_area_sqm": 72.3,
        "layout": "3LDK",
        "built_year": 2005,
        "management_fee_jpy": 11_000,
        "repair_reserve_jpy": 14_500,
        "floor_number": 3,
        "total_floors": 7,
        "total_units": 35,
        "zoning_type": "第一種住居地域",
        "hazard_flag": False,
        "memo": "広め・修繕積立金やや高め",
    },
    {
        "name": "グランドメゾン塚口",
        "source_url": "https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/nc_00003/",
        "address_text": "兵庫県尼崎市塚口町3丁目",
        "station_name": "塚口",
        "walking_minutes": 12,
        "price_jpy": 22_000_000,
        "floor_area_sqm": 61.0,
        "layout": "2LDK",
        "built_year": 1998,
        "management_fee_jpy": 9_500,
        "repair_reserve_jpy": 18_000,
        "floor_number": 2,
        "total_floors": 5,
        "total_units": 20,
        "zoning_type": "第一種住居地域",
        "hazard_flag": True,
        "memo": "価格は安いがハザード区域・築古・修繕積立金高い",
    },
]

property_ids = []
for p in properties_data:
    r = client.post("/properties", json=p)
    assert r.status_code == 201, f"Failed to create property: {r.text}"
    created = r.json()
    property_ids.append(created["id"])
    print(f"✓ Property registered: {created['name']} (ID={created['id']})")


# ---------------------------------------------------------------
# 3. Create loan scenarios for each property
# ---------------------------------------------------------------
loan_configs = [
    # (label, down_payment_jpy, annual_interest_rate, loan_years)
    ("変動金利 0.5% / 頭金10%", 0.10, 0.005, 35),
    ("固定金利 1.5% / 頭金20%", 0.20, 0.015, 35),
]

for pid, pdata in zip(property_ids, properties_data):
    for label, dp_ratio, rate, years in loan_configs:
        dp = int(pdata["price_jpy"] * dp_ratio)
        body = {
            "label": label,
            "down_payment_jpy": dp,
            "annual_interest_rate": rate,
            "loan_years": years,
        }
        r = client.post(f"/properties/{pid}/loan-scenarios", json=body)
        assert r.status_code == 201, f"Loan failed: {r.text}"
        loan = r.json()
        print(
            f"  ✓ Loan [{label}] → 月額 {loan['monthly_payment_jpy']:,}円 "
            f"(借入 {loan['loan_amount_jpy']:,}円)"
        )


# ---------------------------------------------------------------
# 4. Create rental scenarios for each property
# ---------------------------------------------------------------
rent_estimates = [130_000, 110_000, 90_000]  # 想定月額賃料

for pid, rent in zip(property_ids, rent_estimates):
    body = {
        "label": "標準シナリオ",
        "expected_rent_jpy": rent,
        "vacancy_rate": 0.05,
        "management_fee_rate": 0.05,
        "fixed_asset_tax_annual_jpy": 100_000,
        "insurance_annual_jpy": 20_000,
    }
    r = client.post(f"/properties/{pid}/rental-scenarios", json=body)
    assert r.status_code == 201, f"Rental failed: {r.text}"
    rental = r.json()
    cf = rental["monthly_net_cashflow_jpy"]
    sign = "+" if cf >= 0 else ""
    print(f"  ✓ Rental (家賃{rent:,}円) → 月次CF {sign}{cf:,}円")


# ---------------------------------------------------------------
# 5. Calculate exit scores
# ---------------------------------------------------------------
for pid in property_ids:
    r = client.post(f"/properties/{pid}/exit-score/calculate")
    assert r.status_code == 201, f"Exit score failed: {r.text}"
    es = r.json()
    print(f"  ✓ Exit score: {es['total_score']}/100")


# ---------------------------------------------------------------
# 6. Compare all properties
# ---------------------------------------------------------------
r = client.post("/comparison", json={"property_ids": property_ids})
assert r.status_code == 200, f"Comparison failed: {r.text}"
comparison = r.json()

print("\n" + "=" * 60)
print("  物件比較サマリー")
print("=" * 60)
print(f"{'物件名':<20} {'価格':>12} {'月額ローン':>12} {'賃貸CF':>10} {'出口スコア':>10}")
print("-" * 70)
for ps in comparison["properties"]:
    p = ps["property"]
    loan_payment = ps["loan_scenarios"][0]["monthly_payment_jpy"] if ps["loan_scenarios"] else 0
    rental_cf = (
        ps["rental_scenarios"][0]["monthly_net_cashflow_jpy"]
        if ps["rental_scenarios"]
        else 0
    )
    exit_score = ps["exit_score"]["total_score"] if ps["exit_score"] else "-"
    sign = "+" if rental_cf >= 0 else ""
    print(
        f"{p['name']:<20} {p['price_jpy']:>10,}円 "
        f"{loan_payment:>10,}円 "
        f"{sign}{rental_cf:>8,}円 "
        f"{exit_score:>8}/100"
    )

print("\n✓ All E2E tests passed!")
print(f"  Properties: {len(property_ids)}")
print(f"  Loan scenarios: {len(property_ids) * len(loan_configs)}")
print(f"  Rental scenarios: {len(property_ids)}")
print(f"  Exit scores: {len(property_ids)}")
client.close()
