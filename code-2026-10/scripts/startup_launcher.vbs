'''' Hermes Gateway + 看门狗 启动器
' 开机自启: 同时启动gateway服务和看门狗监控
' 看门狗使用pythonw DETACHED_PROCESS，不受TUI崩溃影响

Option Explicit
Dim fso, sh, gateway_vbs, watchdog_py, log_file, ts

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

' 路径
gateway_vbs = "C:\Users\Administrator\AppData\Local\hermes\profiles\mybot\gateway-service\Hermes_Gateway_mybot.vbs"
watchdog_py = "C:\Users\Administrator\AppData\Local\hermes\profiles\mybot\scripts\gateway_watchdog.py"
log_file = "C:\Users\Administrator\AppData\Local\hermes\profiles\mybot\logs\startup.log"

' 日志
Function Log(msg)
    ts = Now()
    Dim f
    On Error Resume Next
    Set f = fso.OpenTextFile(log_file, 8, True)
    If Not Err.Number = 0 Then
        Set f = fso.CreateTextFile(log_file, True)
    End If
    f.WriteLine "[" & ts & "] " & msg
    f.Close
    On Error GoTo 0
End Function

Log "=== Hermes 启动 ==="

' 1. 启动 gateway 服务（原有方式）
If fso.FileExists(gateway_vbs) Then
    sh.Run "wscript.exe """ & gateway_vbs & """", 0, False
    Log "Gateway 服务已启动"
Else
    Log "警告: gateway VBS 不存在: " & gateway_vbs
End If

' 2. 启动看门狗（pythonw DETACHED_PROCESS）
If fso.FileExists(watchdog_py) Then
    ' 先执行一次初始检查
    sh.Run "pythonw.exe """ & watchdog_py & """", 0, False
    Log "看门狗初始检查已触发"
Else
    Log "警告: 看门狗脚本不存在: " & watchdog_py
End If

Log "=== 启动完成 ==="
