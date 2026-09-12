param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Invoke-CheckedCommand {
    param([string]$Command, [string[]]$CommandArgs, [string]$Step)
    & $Command @CommandArgs
    if ($LASTEXITCODE -ne 0) { throw "$Step 失败（退出码 $LASTEXITCODE），安装已停止。" }
}

Push-Location $Root
try {
    foreach ($command in @('python', 'node', 'npm.cmd')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "找不到 $command。请安装 Python 3.11+ 和 Node.js 22.12+，再重新打开终端。"
        }
    }
    Invoke-CheckedCommand 'python' @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)') 'Python 版本检查（需要 3.11+）'
    Invoke-CheckedCommand 'node' @('-e', 'const [a,b]=process.versions.node.split(String.fromCharCode(46)).map(Number); process.exit(a>22 || (a===22 && b>=12) ? 0 : 1)') 'Node.js 版本检查（需要 22.12+）'
    if ($CheckOnly) { Write-Host '环境检查通过。'; return }
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        Invoke-CheckedCommand 'python' @('-m', 'venv', '.venv') '创建 Python 环境'
    }
    $Python = Join-Path $Root '.venv\Scripts\python.exe'
    Invoke-CheckedCommand $Python @('-m', 'pip', 'install', '-c', 'requirements.lock.txt', '-e', '.[test]') '安装 Python 依赖'
    Push-Location frontend
    try {
        Invoke-CheckedCommand 'npm.cmd' @('ci') '安装前端锁定依赖'
        Invoke-CheckedCommand 'npm.cmd' @('run', 'build') '构建前端'
    } finally { Pop-Location }
    Invoke-CheckedCommand $Python @('-m', 'alembic', 'upgrade', 'head') '升级数据库'
    Write-Host '安装完成。双击 启动潮湿雨季.bat 即可使用。' -ForegroundColor Green
} catch {
    Write-Host "安装未完成：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally { Pop-Location }
