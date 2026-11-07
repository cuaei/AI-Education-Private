# 建立 Java 檢查鏡像（只用 JDK，執行學生程式時不需網路）。
# 使用方式（專案根目錄 PowerShell）：.\scripts\setup-java.ps1
#
# 優先以 training/java-runtime/Dockerfile 建立；若 Docker Hub 認證或網路失敗，
# 會退回「拉取官方 JDK 17 鏡像並標記」的方式。兩者的執行行為相同：
# 平台只使用 JDK 與 sh，並以 --user 10001 執行。
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$image = 'course-platform-java:2026.11.5'
Write-Host "建立 $image ..."
docker build -t $image (Join-Path $root 'training\java-runtime')
if ($LASTEXITCODE -eq 0) {
    Write-Host "已完成 Dockerfile 建置。"
} else {
    Write-Warning 'Dockerfile 建置失敗，改用官方 JDK 鏡像並加上相同標記。'
    docker pull eclipse-temurin:17-jdk
    if ($LASTEXITCODE -ne 0) { throw "無法取得 JDK 鏡像。請確認網路與 Docker Desktop。" }
    docker tag eclipse-temurin:17-jdk $image
}
docker image inspect $image --format '{{.Id}}'
Write-Host "完成。可在平台的綜合實作與模擬實習頁實際執行檢查。"
