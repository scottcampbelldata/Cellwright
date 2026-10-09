# SPDX-License-Identifier: EUPL-1.2
import unittest
import os

from migration import runtime, vba
from migration.convert import basic, BASIC_INTRINSICS
from harness.compare import compare


class MigrationTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows extended paths')
    def test_office_extended_paths(self):
        from migration.office import local_path
        self.assertEqual(local_path('\\\\?\\C:\\data\\Book.xlsm').as_uri(),'file:///C:/data/Book.xlsm')
        self.assertEqual(local_path('\\\\?\\UNC\\server\\share\\Book.xlsm').as_uri(),'file://server/share/Book.xlsm')
    def test_python_ast_and_execution(self):
        source = '''Option Explicit
Sub Calculate(ByVal amount As Double)
Dim i As Long, total As Double
For i = 1 To 3
 total = total + amount * i
Next i
If total > 10 Then
 Worksheets("Data").Range("A1").Value = total
Else
 Worksheets("Data").Range("A1").Value = 0
End If
End Sub
'''
        converted = vba.to_python(source)
        self.assertEqual(converted["todos"], [])
        namespace, values = {}, {}
        class Cell:
            value = None
        cell = Cell()
        class Sheet:
            def range(self, address):
                self.address = address
                return cell
        sheet = Sheet()
        exec(converted["source"], namespace)
        namespace["worksheets"] = lambda name: sheet
        namespace["calculate"](2)
        self.assertEqual(cell.value, 12)
        self.assertEqual(sheet.address, "A1")

    def test_comments_strings_and_fail_closed(self):
        converted = vba.to_python('Sub Test()\nDim x As String\nx = "End If: \' Shell"\nOn Error Resume Next\nEnd Sub')
        self.assertEqual(len(converted["todos"]), 1)
        namespace = {}
        exec(converted["source"], namespace)
        with self.assertRaises(NotImplementedError): namespace["test"]()
        self.assertEqual(vba.emit(vba.expression('"A" & "B"')), "_vb.concat('A', 'B')")
        self.assertEqual(list(runtime.for_range(3, 1, -1)), [3, 2, 1])
        self.assertEqual(runtime.right("abc", 0), "")
        with self.assertRaises(NotImplementedError): runtime.coordinates("../bad")

    def test_basic_preserves_unknown_code_and_native_rewrite(self):
        original = 'Attribute VB_Name = "Test"\nSub Calculate()\nWorksheets("Data").Range("A1").Value = 12\nShell "cmd.exe"\nEnd Sub'
        result = basic(original, [], native=True)
        self.assertIn('MFSet MFRange("Data", "A1"), 12', result["source"])
        self.assertIn('Shell "cmd.exe"', result["source"])
        self.assertEqual(len(result["rewrites"]), 1)
        self.assertTrue(basic(original, [])["source"].startswith("Option VBASupport 1"))

    def test_comparison_detects_value_formula_and_missing_cell(self):
        expected = {"sheets": {"Data": {"A1": {"value": 1.0, "formula": "=SUM(B1;B2)"}}}}
        same = {"sheets": {"Data": {"A1": {"value": 1.0000000001, "formula": "=sum(B1,B2)"}}}}
        self.assertTrue(compare(expected, same)["passed"])
        same['sheets']['Data']['A1']['formula']=' = sum ( B1 , B2 ) '
        self.assertTrue(compare(expected,same)['passed'])
        from harness.compare import formula_tokens
        self.assertNotEqual(formula_tokens('={1;2}'),formula_tokens('={1,2}'))
        self.assertNotEqual(formula_tokens('="a b"'),formula_tokens('="ab"'))
        same["sheets"]["Data"]["A1"]["value"] = 10
        self.assertFalse(compare(expected, same)["passed"])
        self.assertFalse(compare(expected, {"sheets": {}})["passed"])
        self.assertFalse(compare({"sheets": {}}, {"sheets": {}})["passed"])

    def test_python_semantic_limits_and_formula_copy(self):
        self.assertEqual(vba.emit(vba.expression('Date')), '_vb.date()')
        self.assertEqual(vba.emit(vba.expression('Now()')), '_vb.now()')
        self.assertEqual(vba.emit(vba.expression('VBA.Date')), '_vb.date()')
        self.assertTrue(vba.to_python('Option Compare Text\nSub Test()\nEnd Sub')['todos'])
        self.assertEqual(vba.emit(vba.expression('eval("x")')), "_mf_eval('x')")
        with self.assertRaises(vba.Unsupported):vba.expression('('*150+'1'+')'*150)
        self.assertTrue(vba.to_python('Sub Test(x As Long)\nx=1\nEnd Sub')['todos'])
        import openpyxl
        book=runtime.Workbook(openpyxl.Workbook())
        sheet=book.worksheets(1)
        sheet.range('A1').formula='=B1'
        with self.assertRaises(NotImplementedError):sheet.range('A1').copy(sheet.range('A2'))
        self.assertIsNone(sheet.range('A2').value)

    def test_forty_basic_intrinsic_rules_preserve_strings_and_comments(self):
        self.assertEqual(len(BASIC_INTRINSICS),40)
        for name in BASIC_INTRINSICS:
            source='Sub Test()\nx = VBA.'+name+'(1)\nx = "VBA.'+name+'(1)"\n\x27 VBA.'+name+'(1)\nEnd Sub'
            result=basic(source,[])
            self.assertEqual(len(result['rewrites']),1)
            self.assertIn('x = '+name+'(1)',result['source'])
            self.assertIn('"VBA.'+name+'(1)"',result['source'])
        result=basic('Dim VBA As Object\nSub Test()\nx = VBA.Len(1)\nEnd Sub',[])
        self.assertFalse(result['rewrites'])
        self.assertTrue(result['todos'])


if __name__ == "__main__": unittest.main()
