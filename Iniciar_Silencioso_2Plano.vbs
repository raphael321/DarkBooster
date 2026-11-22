Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir

strArgs = ""
If WScript.Arguments.Count > 0 Then
    strArgs = " " & WScript.Arguments(0)
End If

On Error Resume Next
WshShell.Run "pythonw.exe """ & strDir & "\app.py""" & strArgs, 0, False
If Err.Number <> 0 Then
    Err.Clear
    WshShell.Run "pyw.exe """ & strDir & "\app.py""" & strArgs, 0, False
    If Err.Number <> 0 Then
        Err.Clear
        WshShell.Run """" & strDir & "\Instalar_e_Abrir_DarkBooster.bat""", 1, False
    End If
End If
On Error GoTo 0
