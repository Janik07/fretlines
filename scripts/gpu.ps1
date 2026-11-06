# Разбор на видеокарте NVIDIA: ставит PyTorch с CUDA вместо CPU-сборки (~2.5 ГБ).
# «gpu.bat off» возвращает CPU-сборку.
param([string]$Mode = "on")
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root
Ensure-Uv

$marker = Join-Path $Tools "gpu"
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Fail "Сначала запусти start.bat — он подготовит окружение." }

if ($Mode -eq "off") {
    Step "Возвращаю CPU-сборку PyTorch"
    & $Uv sync --frozen --no-dev --inexact --reinstall-package torch --reinstall-package torchaudio
    if ($LASTEXITCODE -ne 0) { Fail "Не получилось вернуть CPU-сборку." }
    Remove-Item $marker -ErrorAction SilentlyContinue
    Write-Host "  Готово: разбор снова на процессоре." -ForegroundColor Green
    exit 0
}

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Fail "Не вижу видеокарту NVIDIA (нет nvidia-smi). Без неё всё работает на процессоре."
}
Step "Скачиваю PyTorch с CUDA — это около 2.5 ГБ, можно пойти за чаем"
& $Uv pip install --python $python --index-url "https://download.pytorch.org/whl/cu128" "torch==2.11.0+cu128" "torchaudio==2.11.0+cu128"
if ($LASTEXITCODE -ne 0) { Fail "Не удалось поставить PyTorch с CUDA. Попробуй ещё раз — загрузка продолжится." }
New-Item -ItemType File -Path $marker -Force | Out-Null
& $python -c "import torch; print('  CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
Write-Host "  Готово: следующие разборы пойдут на видеокарте." -ForegroundColor Green
