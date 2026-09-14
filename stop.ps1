# AI-Chief-Master 一键停止脚本
# 用法：右键 -> 使用 PowerShell 运行，或在 PowerShell 中执行 .\stop.ps1

$ProjectDir = "D:\AI-chief-master"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI-Chief-Master 一键停止" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查项目目录
if (-not (Test-Path $ProjectDir)) {
    Write-Host "  项目目录不存在: $ProjectDir" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Set-Location $ProjectDir

# 确认
Write-Host "即将停止所有容器（数据不会丢失）" -ForegroundColor Yellow
$confirm = Read-Host "确认停止？(Y/n)"
if ($confirm -eq "n" -or $confirm -eq "N") {
    Write-Host "已取消" -ForegroundColor Gray
    exit 0
}

Write-Host ""
Write-Host "正在停止容器..." -ForegroundColor Yellow
docker compose down

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  所有容器已停止" -ForegroundColor Green
    Write-Host "  数据卷保留，下次启动数据仍在" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan
} else {
    Write-Host "  停止过程中出现错误" -ForegroundColor Red
}

Write-Host ""
Read-Host "按回车键退出"
