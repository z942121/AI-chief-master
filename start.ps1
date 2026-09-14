# AI-Chief-Master 一键启动脚本
# 用法：右键 -> 使用 PowerShell 运行，或在 PowerShell 中执行 .\start.ps1

$ProjectDir = "D:\AI-chief-master"
$FrontendUrl = "http://localhost:8080"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI-Chief-Master 一键启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Docker 是否运行
Write-Host "[1/5] 检查 Docker 状态..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Docker 未运行，请先启动 Docker Desktop" -ForegroundColor Red
        Read-Host "按回车键退出"
        exit 1
    }
    Write-Host "  Docker 运行正常" -ForegroundColor Green
} catch {
    Write-Host "  Docker 未安装或未运行" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

# 2. 检查项目目录
Write-Host "[2/5] 检查项目目录..." -ForegroundColor Yellow
if (-not (Test-Path $ProjectDir)) {
    Write-Host "  项目目录不存在: $ProjectDir" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
if (-not (Test-Path "$ProjectDir\docker-compose.yml")) {
    Write-Host "  docker-compose.yml 不存在" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
Write-Host "  项目目录正常" -ForegroundColor Green

# 3. 启动容器
Write-Host "[3/5] 启动 Docker 容器..." -ForegroundColor Yellow
Set-Location $ProjectDir
docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "  容器启动失败，请检查 docker compose 日志" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
Write-Host "  容器启动指令已发送" -ForegroundColor Green

# 4. 等待服务就绪
Write-Host "[4/5] 等待服务就绪（约 30 秒）..." -ForegroundColor Yellow
$maxWait = 60
$waited = 0
$mysqlReady = $false
$backendReady = $false

while ($waited -lt $maxWait) {
    # 检查 MySQL health
    $mysqlStatus = docker compose ps --format json mysql 2>&1 | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($mysqlStatus -and $mysqlStatus.State -eq "running" -and $mysqlStatus.Health -eq "healthy") {
        $mysqlReady = $true
    }

    # 检查 Backend
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080/api/v1/health" -Method Get -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
        }
    } catch {
        # 后端还没就绪
    }

    if ($mysqlReady -and $backendReady) {
        Write-Host "  所有服务已就绪！" -ForegroundColor Green
        break
    }

    Write-Host "  等待中... ($waited`s) MySQL: $(if($mysqlReady){'OK'}else{'...'}) Backend: $(if($backendReady){'OK'}else{'...'})"
    Start-Sleep -Seconds 5
    $waited += 5
}

if (-not $mysqlReady -or -not $backendReady) {
    Write-Host "  警告：服务可能未完全就绪，请稍后再试" -ForegroundColor Yellow
}

# 5. 显示状态并打开浏览器
Write-Host "[5/5] 服务状态：" -ForegroundColor Yellow
docker compose ps
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动完成！" -ForegroundColor Green
Write-Host "  访问地址: $FrontendUrl" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 询问是否打开浏览器
$open = Read-Host "是否在浏览器中打开？(Y/n)"
if ($open -ne "n" -and $open -ne "N") {
    Start-Process $FrontendUrl
}

Write-Host ""
Write-Host "常用命令：" -ForegroundColor Gray
Write-Host "  查看日志: docker compose logs -f backend" -ForegroundColor Gray
Write-Host "  停止服务: docker compose down" -ForegroundColor Gray
Write-Host "  重启服务: docker compose restart" -ForegroundColor Gray
Write-Host ""
Read-Host "按回车键退出"
