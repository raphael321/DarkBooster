Set WshShell = CreateObject("WScript.Shell")
strDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir

strArgs = ""
If WScript.Arguments.Count > 0 Then
    strArgs = " " & WScript.Arguments(0)
End If

strPythonW = "C:\Users\rapha\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
WshShell.Run """" & strPythonW & """ """ & strDir & "\app.py""" & strArgs, 0, False
