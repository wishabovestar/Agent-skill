' HermesGatewayWatchdog 计划任务安装脚本
' 以管理员权限创建Windows计划任务（每3分钟检查gateway存活）
' 用法: wscript.exe install_watchdog.vbs

Set shell = CreateObject("Shell.Application")
' 以管理员权限运行schtasks
shell.ShellExecute "schtasks", "/Create /F /SC MINUTE /MO 3 /TN HermesGatewayWatchdog /TR ""pythonw.exe C:\Users\Administrator\AppData\Local\hermes\profiles\mybot\scripts\gateway_watchdog.py"" /ST 00:00 /RL HIGHEST", "", "runas", 0

WScript.Echo "计划任务安装请求已发送，请在弹出的UAC窗口中确认"
WScript.Echo "确认后运行: schtasks /Query /TN HermesGatewayWatchdog 验证"
