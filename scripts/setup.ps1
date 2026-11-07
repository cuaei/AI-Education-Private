$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
    else { throw '需要先安装 Python 3.12 或更新版本。' }
    if ($LASTEXITCODE -ne 0) { throw '建立 Python 环境失败。' }
}
& $pythonPath -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw '後端依赖安装失败。' }
Push-Location frontend
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。' }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw '网页构建失败。' }
} finally { Pop-Location }
Write-Host '安装完成。执行 .\scripts\start.ps1 启动。'
