$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "运行环境不存在，请先执行安装潮湿雨季.bat"
}
Set-Location -LiteralPath $root
& $python -c "from backend.app.trend_scheduler import uninstall_schedule; print(uninstall_schedule())"
