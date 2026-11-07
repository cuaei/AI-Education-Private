$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& (Join-Path $projectRoot '.venv/Scripts/python.exe') scripts/make_engineering_materials.py
if ($LASTEXITCODE -ne 0) { throw '课程材料生成失败。' }
docker build -t career-studio-engineering:2026.10.12 training/software-engineering
if ($LASTEXITCODE -ne 0) { throw '镜像构建失败，请检查Docker Desktop及网络。' }
Write-Host '软件工程运行环境已准备。未执行学生提交或自动测试。'
