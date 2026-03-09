# Home Decision OS - Docker 動作確認スクリプト (PowerShell)
# 使い方: .\backend\scripts\run_tests_in_docker.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Home Decision OS - 動作確認" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n[1/4] ヘルスチェック..." -ForegroundColor Yellow
$health = Invoke-RestMethod -Uri "http://localhost:8000/health" -ErrorAction SilentlyContinue
if ($health.status -eq "ok") {
    Write-Host "  OK: API is running" -ForegroundColor Green
} else {
    Write-Host "  FAIL: API is not running. Run 'docker compose up --build' first." -ForegroundColor Red
    exit 1
}

Write-Host "`n[2/4] pytest 実行（Docker内）..." -ForegroundColor Yellow
docker compose exec api pip install httpx pytest pytest-cov -q 2>$null
docker compose exec api pytest tests/test_domain/ -v --tb=short

Write-Host "`n[3/4] E2E テスト実行（Docker内）..." -ForegroundColor Yellow
docker compose exec api python scripts/test_api_e2e.py

Write-Host "`n[4/4] Swagger UI 確認" -ForegroundColor Yellow
Write-Host "  ブラウザで開いてください: http://localhost:8000/docs" -ForegroundColor Cyan

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  完了!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
