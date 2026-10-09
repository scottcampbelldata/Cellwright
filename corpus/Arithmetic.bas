' SPDX-License-Identifier: EUPL-1.2
Option Explicit

Sub Calculate(ByVal amount As Double)
    Dim i As Long
    Dim total As Double
    For i = 1 To 3
        Worksheets("Data").Cells(i, 1).Value = amount * i
        total = total + amount * i
    Next i
    If total > 10 Then
        Worksheets("Data").Range("A5").Value = total
    Else
        Worksheets("Data").Range("A5").Value = 0
    End If
    Worksheets("Data").Range("B1").Formula = "=SUM(A1:A3)"
    Worksheets("Data").Range("C1").Value = UCase("macro ferry") & ":" & CStr(total)
    Worksheets("Data").Range("D1").Value = DoubleIt(amount)
End Sub

Function DoubleIt(ByVal amount As Double) As Double
    DoubleIt = amount * 2
End Function
