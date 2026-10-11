# SPDX-License-Identifier: EUPL-1.2
"""Regression checks use source, XML and owned blank books; no workbook routine runs."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from migration import ui,runtime,vba
from migration.checklist import checklist,handoff
from migration.convert import basic
from dashboard.setup import check
from test_controls import Container,event
from migration.controls import rebind

SPEC={'name':'EntryForm','scope':'dialog','controls':[{'name':'Amount','control_type':'TextBox'},{'name':'Apply','control_type':'CommandButton'}],'error':None}
SOURCE='Private Sub Apply_Click()\nWorksheets("Data").Range("A1").Value = Me.Amount.Value\nMe.Amount.Value = ""\nMe.Hide\nEnd Sub\n'
XML=('<?xml version="1.0"?><dlg:window xmlns:dlg="'+ui.DLG+'" xmlns:script="'+ui.SCRIPT+'" dlg:id="EntryForm" dlg:left="0" dlg:top="0" dlg:width="120" dlg:height="80"><dlg:bulletinboard><dlg:textfield dlg:id="Amount" dlg:tab-index="0" dlg:left="10" dlg:top="10" dlg:width="50" dlg:height="12"/><dlg:button dlg:id="Apply" dlg:tab-index="1" dlg:left="10" dlg:top="40" dlg:width="40" dlg:height="12"><script:event script:macro-name="application:untrusted"/></dlg:button></dlg:bulletinboard></dlg:window>').encode()


class FirstMigrationTests(unittest.TestCase):
    def test_form_rewrites_are_local_and_preserve_unresolved_source(self):
        result=ui.rewrite(SOURCE,'EntryForm',[SPEC])
        self.assertFalse(result['todos'])
        self.assertIn('MFUIGet(MFUIControl("dialog", "EntryForm", "Amount", "TextBox"), "value")',result['source'])
        self.assertIn('MFUIHide "EntryForm"',result['source'])
        self.assertFalse(basic(result['source'],[],True)['todos'])
        for source in ['Me.Amount.AddItem "x"','Me.Amount.PasswordChar = "*"','Me.Controls("Amount").Value = 3','EntryForm.Show 0','Me.Amount.Value = 1: Me.Hide']:
            result=ui.rewrite(source,'EntryForm',[SPEC]);self.assertTrue(result['todos']);self.assertIn(source,result['source'])
        quoted=ui.rewrite('Sub Test()\nx = "Me.Amount.Value"\nEnd Sub','Module1',[SPEC])
        self.assertFalse(quoted['todos'] or quoted['rewrites'])

    def test_dialog_strips_existing_events_and_binds_only_eligible_controls(self):
        callbacks=ui.bindings({'source':SOURCE},SPEC)
        callbacks[0]['wrapper']='MFUIEvent1'
        xml,records,good=ui.dialog_candidate(XML,SPEC,callbacks)
        self.assertTrue(good);self.assertNotIn('application:untrusted',xml)
        self.assertIn('Standard.EntryForm.MFUIEvent1',xml)
        self.assertIn('dlg:width="120"',xml)
        self.assertEqual(sum(r['status']=='rewritten' for r in records),1)
        unsupported={**SPEC,'controls':SPEC['controls']+[{'name':'Tree','control_type':'CustomOrUnknown'}]}
        xml,records,good=ui.dialog_candidate(XML,unsupported,callbacks)
        self.assertFalse(good);self.assertNotIn('Standard.EntryForm.MFUIEvent1',xml)
        with self.assertRaises(ValueError):ui.dialog_candidate(b'<!DOCTYPE x [<!ENTITY bad "xx">]><x/>',SPEC,[])
        with self.assertRaises(ValueError):ui.dialog_candidate(XML.replace(b'dlg:id="Apply"',b'dlg:id="Amount"'),SPEC,[])
        with self.assertRaises(ValueError):ui.dialog_candidate(XML.replace(b' dlg:tab-index="1"',b''),SPEC,[])
        lifecycle=ui.bindings({'source':'Private Sub UserForm_Initialize()\nEnd Sub'},SPEC)
        self.assertEqual(lifecycle[0]['status'],'manual')

    def test_activex_button_uses_source_matched_private_handler_without_invocation(self):
        source='Private Sub Apply_Click()\nWorksheets("Data").Range("A1").Value = 1\nEnd Sub'
        spec={'name':'Sheet1','scope':'sheet','controls':[{'name':'Apply','control_type':'CommandButton'}]}
        spec['callbacks']=ui.bindings({'source':source},spec);spec['callbacks'][0]['wrapper']='MFUIEvent1'
        button=SimpleNamespace(Name='Apply',ButtonType=SimpleNamespace(value='PUSH'),Toggle=False,TargetURL='',supportsService=lambda name:name.endswith('CommandButton'))
        form=Container([button],{0:(event(code='untrusted'),)})
        sheet=SimpleNamespace(Name='Data',CodeName='Sheet1',DrawPage=SimpleNamespace(Forms=form))
        doc=SimpleNamespace(Sheets=SimpleNamespace(Count=1,getByIndex=lambda i:sheet),getScriptProvider=Mock(side_effect=AssertionError('Must never run')))
        result=rebind(doc,[],'Book.xlsm',[],SimpleNamespace(createUnoStruct=lambda _:SimpleNamespace()),[spec])
        self.assertEqual(result['records'][0]['status'],'rewritten')
        self.assertEqual(form.events[0][0].ScriptCode,'vnd.sun.star.script:Standard.Sheet1.MFUIEvent1?language=Basic&location=document')
        doc.getScriptProvider.assert_not_called()
        button.supportsService=lambda name:False
        result=rebind(doc,[],'Book.xlsm',[],SimpleNamespace(createUnoStruct=lambda _:SimpleNamespace()),[spec])
        self.assertTrue(all(r['status']=='manual' for r in result['records']));self.assertFalse(form.events[0])

    def test_range_candidates_parse_named_arguments_and_compile_without_running(self):
        source='Sub Work()\nWorksheets("Data").Range("A1:B4").Sort Key1:=Worksheets("Data").Range("A1"), Order1:=xlAscending, Header:=xlYes\nWorksheets("Data").Range("A1:B4").AutoFilter Field:=1, Criteria1:="Open"\nWorksheets("Data").Range("A1:B4").Copy Destination:=Worksheets("Data").Range("D1")\nWorksheets("Data").Range("A1:B4").ClearContents\nEnd Sub'
        result=basic(source,[],True);self.assertFalse(result['todos']);self.assertEqual(len(result['rewrites']),4)
        result=vba.to_python(source);self.assertFalse(result['todos']);compile(result['source'],'candidate','exec')
        self.assertIn('.sort(worksheets(\'Data\').range(\'A1\'), 1, 1)',result['source'])
        self.assertTrue(vba.to_python(source.replace('Header:=xlYes','Header:=xlGuess'))['todos'])
        shadowed=source.replace('Sub Work()','Sub Work()\nDim xlAscending As Integer')
        self.assertTrue(basic(shadowed,[],True)['todos']);self.assertTrue(vba.to_python(shadowed)['todos'])
        malformed=source.replace('Header:=xlYes','MatchCase:=True')
        self.assertTrue(basic(malformed,[],True)['todos']);self.assertTrue(vba.to_python(malformed)['todos'])
        compound='Worksheets("Data").Range("A1").ClearContents: x = 42'
        result=basic(compound,[],True)
        self.assertTrue(result['todos']);self.assertIn(compound,result['source'])
        reordered=source.replace('Key1:=Worksheets("Data").Range("A1"), Order1:=xlAscending, Header:=xlYes','Header:=xlYes, Order1:=xlAscending, Key1:=Worksheets("Data").Range("A1")')
        self.assertIn(".sort(worksheets('Data').range('A1'), 1, 1)",vba.to_python(reordered)['source'])
        positional=source.replace('Key1:=Worksheets("Data").Range("A1"), Order1:=xlAscending, Header:=xlYes','Worksheets("Data").Range("A1"), xlAscending, xlYes')
        self.assertTrue(vba.to_python(positional)['todos'])

    def test_native_sort_uses_typed_fields_and_accepts_numeric_formula_text(self):
        native=Mock()
        sheet=SimpleNamespace(name='Data',book=SimpleNamespace(uno=True),native=SimpleNamespace(getCellRangeByName=lambda address:native),read=lambda row,column,formula=False:str(row) if formula else row)
        uno=SimpleNamespace(createUnoStruct=lambda name:SimpleNamespace(),Enum=lambda typ,value:value,Any=lambda typ,value:(typ,value))
        runner=SimpleNamespace(property_value=lambda name,value:SimpleNamespace(Name=name,Value=value))
        with patch.dict(sys.modules,{'uno':uno,'harness.libreoffice.runner':runner}):
            runtime.Range(sheet,(1,1,4,2)).sort(runtime.Range(sheet,(1,1,1,1)),1,1)
        runtime.Range(sheet,(1,1,4,2)).clear()
        native.clearContents.assert_called_once_with(887)
        properties={prop.Name:prop.Value for prop in native.sort.call_args.args[0]}
        self.assertEqual(properties['SortFields'][0],'[]com.sun.star.table.TableSortField')
        self.assertEqual(properties['SortFields'][1][0].Field,0)
        self.assertTrue(properties['ContainsHeader'])

    def test_control_inventory_retains_expansion_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'owned.xlsm'
            with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><controls><control name="Apply"/></controls></worksheet>')
                archive.writestr('xl/worksheets/_rels/sheet1.xml.rels',b'x'*(16*1024*1024+1))
            with self.assertRaisesRegex(ValueError,'archive limits'):ui.inventory({},path)

    def test_blank_workbook_adapter_operations_validate_before_changes(self):
        import openpyxl
        book=runtime.Workbook(openpyxl.Workbook());sheet=book.worksheets(1);sheet.name='Data'
        sheet.range('A1:B4').value=(('key','status'),(3,'Closed'),(1,'Open'),(2,'Open'))
        sheet.range('A1:B4').sort(sheet.range('A1'),1,1)
        self.assertEqual(sheet.range('A2:A4').value,((1,),(2,),(3,)))
        sheet.range('A1:B4').autofilter(2,'open')
        self.assertTrue(sheet.native.row_dimensions[4].hidden);self.assertFalse(sheet.native.row_dimensions[2].hidden)
        sheet.range('A1:B4').copy(sheet.range('D1'))
        self.assertEqual(sheet.range('D2').value,1)
        with self.assertRaises(NotImplementedError):sheet.range('A1:B4').autofilter(2,'O*')
        with self.assertRaises(ValueError):sheet.range('A1:XFD100').clear()
        sheet.range('D1:E4').clear();self.assertIsNone(sheet.range('D2').value)
        new=book.worksheets.add();new.name='Summary';self.assertEqual(book.active.name,'Summary')
        with self.assertRaises(ValueError):new.name='data'
        sheet.range('A2').formula='=1+2'
        before=sheet.range('B2').value
        with self.assertRaises(NotImplementedError):sheet.range('A1:B4').sort(sheet.range('A1'),1,1)
        self.assertEqual(sheet.range('B2').value,before)

    def test_checklist_unknown_and_handoff_do_not_export_sensitive_fields(self):
        report={'target':'basic','input':'C:/Secret/Customer.xlsm','modules':[{'name':'CustomerAccount','kind':'standard','todos':[{'line':4,'reason':'Shell sensitive command'}],'rewrites':[],'procedures':[{'name':'PrivateClientRoutine'}],'source':'private code'}], 'workbook_findings':[{'rule_id':'MF060','verdict':'unknown','messages':['Oversized part skipped'],'line':None}]}
        report['checklist']=checklist(report)
        self.assertEqual(report['checklist']['coverage_status'],'unknown');self.assertEqual(report['checklist']['test_status'],'not_tested')
        value=handoff(report,[{'passed':True}]);serialized=json.dumps(value)
        for secret in ['Secret','CustomerAccount','PrivateClientRoutine','private code','sensitive command']:self.assertNotIn(secret,serialized)
        self.assertEqual(value['test_status'],'selected_tests_passed')
        self.assertEqual(handoff(report,include_identifiers=True)['modules'][0]['label'],'CustomerAccount')
        self.assertTrue(all(item['next_action'] for item in report['checklist']['items']))

    def test_invalid_verification_fields_are_rejected_before_macro_execution(self):
        from migration.verify import validate,verify
        case={'original':{'macro':'Module.Run','inputs':[]},'converted':{'macro':'Standard.Module.Run','inputs':[]},'ranges':{'Data':['A1:B2']}}
        validate(case)
        for value in [{'Data':['A0']},{'Data':['A1:XFD100']},[],{'Data':'A1'}]:
            with self.subTest(value=value),patch('migration.verify.excel') as excel,patch('migration.verify.office.run') as worker:
                with self.assertRaises((ValueError,NotImplementedError)):verify(dict(case,ranges=value),'unused',True)
                excel.assert_not_called();worker.assert_not_called()
        with self.assertRaises(ValueError):validate({**case,'original':{'macro':'Module.Run','inputs':[float('nan')]}})

    def test_setup_checks_do_not_open_office_or_execute_workbooks(self):
        with tempfile.TemporaryDirectory() as temporary,patch('dashboard.setup.office.program',side_effect=FileNotFoundError),patch('dashboard.setup.subprocess.run') as worker:
            binary=Path(temporary)/'scanner';binary.write_bytes(b'placeholder')
            result=check(binary)
            self.assertTrue(result['first_scan_ready']);self.assertFalse(next(c for c in result['checks'] if c['id']=='libreoffice')['available'])
            worker.assert_not_called()
            self.assertNotIn('consulting_url',result)
