@echo off
REM HermesGatewayWatchdog 计划任务安装
REM 以管理员身份运行此文件
REM 用法: 右键 → 以管理员身份运行

echo ==================================
echo 安装 Hermes Gateway 看门狗
echo 每3分钟检查一次gateway状态
echo ==================================

schtasks /Create /F /SC MINUTE /MO 3 /TN HermesGatewayWatchdog /TR "pythonw.exe C:\Users\Administrator\AppData\Local\hermes\profiles\mybot\scripts\gateway_watchdog.py" /ST 00:00 /RL HIGHEST

if %ERRORLEVEL% EQU 0 (
    echo [OK] 计划任务安装成功
    echo 查看: schtasks /Query /TN HermesGatewayWatchdog
) else (
    echo [FAIL] 安装失败，错误码: %ERRORLEVEL%
    echo 请以管理员身份运行!
)

pause
