# Запуск Fretlines. Первый раз ставит Python 3.11, библиотеки и собирает интерфейс — дальше
# стартует за пару секунд. Аргументы передаются дальше: start.bat --host 0.0.0.0 --port 8090
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root

Write-Host ""
Write-Host "  FRETLINES" -ForegroundColor White
Write-Host ""

Ensure-Uv

$gpu = Test-Path (Join-Path $Tools "gpu")
Step "Проверяю библиотеки Python (первый раз — несколько минут)"
if ($gpu) {
    & $Uv sync --frozen --no-dev --inexact --no-install-package torch --no-install-package torchaudio
} else {
    & $Uv sync --frozen --no-dev --inexact
}
if ($LASTEXITCODE -ne 0) { Fail "Не удалось поставить библиотеки Python. Проверь интернет и запусти ещё раз." }

$frontend = Join-Path $Root "frontend"
$index = Join-Path $frontend "dist\index.html"
$stale = -not (Test-Path $index)
if (-not $stale) {
    $built = (Get-Item $index).LastWriteTime
    $newer = Get-ChildItem (Join-Path $frontend "src"), (Join-Path $frontend "index.html"), (Join-Path $frontend "package-lock.json") -Recurse -File |
        Where-Object { $_.LastWriteTime -gt $built } | Select-Object -First 1
    $stale = $null -ne $newer
}
if ($stale) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Fail "Чтобы собрать интерфейс, нужен Node.js 20 или новее: https://nodejs.org (после установки запусти start.bat ещё раз)."
    }
    Push-Location $frontend
    if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
        Step "Ставлю библиотеки интерфейса"
        & npm ci --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Не удалось поставить библиотеки интерфейса." }
    }
    Step "Собираю интерфейс"
    & npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Интерфейс не собрался." }
    Pop-Location
}

Step "Запускаю — браузер откроется сам"
& $Uv run --no-sync python -m fretlines_api @args
