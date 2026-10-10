Sub FormatSheet()
With Worksheets("Data").Range("A1:B2")
 .Font.Bold = True
 With .Font
  .Color = RGB(255, 0, 1)
 End With
 .NumberFormat = "0.00"
End With
End Sub
