# AutoBranch 一键启动脚本
# 固定端口: 后端 8001 / 前端 5174（避开 NexusOps 的 8000/5173）
# 作用: 自动检测并杀掉旧的 AutoBranch 前后端进程 -> 重新启动前后端
# 用法: powershell -ExecutionPolicy Bypass -File .\dev-restart.ps1

$ErrorActionPreference = "Continue"

$BACKEND_PORT = 8001
$FRONTEND_PORT = 5174
$PYTHON = "D:\programming\environment\miniforge3\envs\autobranch\python.exe"
$PROJECT_ROOT = "D:\programming\code\AutoBranch"
$FRONTEND_DIR = "D:\programming\code\AutoBranch\autobranch\frontend"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AutoBranch 一键启动 (后端 8001 / 前端 5174)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---------- 1. 杀掉旧的 AutoBranch 后端进程（含 uvicorn / spawn_main worker） ----------
Write-Host "`n[1/5] 检测并停止旧后端进程..." -ForegroundColor Yellow
$backendProcs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'autobranch\.server\.main' -or
    ($_.CommandLine -match 'spawn_main' -and $_.CommandLine -match 'autobranch')
}
if ($backendProcs) {
    foreach ($p in $backendProcs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  - 已停止后端进程 PID=$($p.ProcessId)"
    }
} else {
    Write-Host "  - 没有运行中的后端进程"
}
# 兜底: 杀掉监听 8001 端口的 python 进程
foreach ($procId in (Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'python' -and $_.CommandLine -match '8001' }).ProcessId) {
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# ---------- 2. 杀掉旧的 AutoBranch 前端进程 ----------
Write-Host "`n[2/5] 检测并停止旧前端进程..." -ForegroundColor Yellow
$frontProcs = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -match 'node' -and $_.CommandLine -match 'vite') -or
    ($_.CommandLine -match 'autobranch\\frontend') -or
    ($_.CommandLine -match 'npm run dev')
}
if ($frontProcs) {
    foreach ($p in $frontProcs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  - 已停止前端进程 PID=$($p.ProcessId)"
    }
} else {
    Write-Host "  - 没有运行中的前端进程"
}

# ---------- 3. 等待端口释放 ----------
Write-Host "`n[3/5] 等待端口释放..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
foreach ($port in @($BACKEND_PORT, $FRONTEND_PORT)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host "  - 端口 $port 仍被 PID $($conn.OwningProcess) 占用，尝试强制释放..."
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    $conn2 = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn2) {
        Write-Host "  - 警告: 端口 $port 仍被占用 (PID $($conn2.OwningProcess))，无法释放。请手动关闭后重试。" -ForegroundColor Red
    } else {
        Write-Host "  - 端口 $port 已释放"
    }
}

# ---------- 4. 启动后端 (FastAPI, 8001) ----------
Write-Host "`n[4/5] 启动后端服务..." -ForegroundColor Yellow
# 检查 LLM 密钥：优先环境变量，其次 autobranch.config.json 的 api_key
if (-not $env:AUTOBRANCH_LLM_API_KEY) {
    try {
        $cfg = Get-Content "$PROJECT_ROOT\autobranch.config.json" -Raw | ConvertFrom-Json
        if ($cfg.llm.api_key) {
            $env:AUTOBRANCH_LLM_API_KEY = $cfg.llm.api_key
            Write-Host "  - 已从 autobranch.config.json 读取 api_key"
        }
    } catch { }
}
if ($env:AUTOBRANCH_LLM_API_KEY) {
    Write-Host "  - LLM 密钥已就绪（可执行真实行为树）"
} else {
    Write-Host "  - 警告: 未配置 LLM 密钥。执行行为树将报『未配置 LLM API 密钥』。" -ForegroundColor Yellow
    Write-Host "    解决: 在 autobranch.config.json 填入 llm.api_key（内部工具，简单优先），或先执行 \$env:AUTOBRANCH_LLM_API_KEY=\"sk-...\" 再运行本脚本。" -ForegroundColor Yellow
}
Start-Process -FilePath $PYTHON -ArgumentList "-m uvicorn autobranch.server.main:app --host 127.0.0.1 --port $BACKEND_PORT" -WorkingDirectory $PROJECT_ROOT -WindowStyle Normal
Write-Host "  - 后端启动中 (http://localhost:$BACKEND_PORT)"

Start-Sleep -Seconds 3

# ---------- 5. 启动前端 (Vite dev, 5174) ----------
Write-Host "`n[5/5] 启动前端服务..." -ForegroundColor Yellow
Start-Process cmd -ArgumentList "/c cd /d $FRONTEND_DIR && npm run dev" -WindowStyle Normal
Write-Host "  - 前端启动中 (http://localhost:$FRONTEND_PORT)"

Write-Host "`n等待服务就绪..." -ForegroundColor Gray
$healthOK = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$BACKEND_PORT/api/health" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $healthOK = $true; break }
    } catch { }
}
if ($healthOK) {
    Write-Host "`n[√] 后端服务已就绪: http://localhost:$BACKEND_PORT/api/health" -ForegroundColor Green
} else {
    Write-Host "`n[!] 后端服务健康检查未通过，请查看启动日志" -ForegroundColor Red
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  启动完成!" -ForegroundColor Green
Write-Host "  前端: http://localhost:$FRONTEND_PORT" -ForegroundColor Green
Write-Host "  后端: http://localhost:$BACKEND_PORT (Swagger: /docs)" -ForegroundColor Green
Write-Host "  后端 API: http://localhost:$BACKEND_PORT/api/health" -ForegroundColor Green
Write-Host "  (端口已避开 NexusOps: 本机 8000/5173 为 NexusOps 使用，AutoBranch 用 8001/5174)" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan