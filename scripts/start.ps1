$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先执行 scripts/setup.ps1 安装依赖。' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw '请先执行 scripts/setup.ps1 构建网页。' }
Write-Host '我要实习：打开 http://127.0.0.1:8000 。按 Ctrl+C 停止服务。'
& $pythonPath -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
