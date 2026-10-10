# SPDX-License-Identifier: EUPL-1.2
import json
import copy
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from unittest.mock import patch
from pathlib import Path

from dashboard.server import Server, Store, validate_paths
from dashboard.localization import conversion_response, handoff_response, setup_response, translate
from migration.checklist import checklist, handoff


class DashboardTests(unittest.TestCase):
    def test_schedule_and_assignments_persist(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary, 'cellwright')
            try:
                store.assignment({'path':'budget.xlsm','owner':'Finance','state':'in_review','notes':'Needs owner review'})
                self.assertEqual(store.list('assignments')[0]['owner'],'Finance')
                store.schedule({'paths':['finance'],'interval_hours':1,'label':'Finance'})
                submitted=[]
                store.submit=lambda *args: submitted.append(args)
                due=store.list('schedules')[0]['next_run']
                self.assertEqual(store.due(due-1),0)
                self.assertEqual(store.due(due),1)
                self.assertEqual(len(submitted),1)
                self.assertEqual(submitted[0][3]['lang'],'en')
                self.assertEqual(store.due(due),0)
                with self.assertRaises(ValueError):store.assignment({'path':'x','state':'invented'})
                with self.assertRaises(ValueError):validate_paths(['x\0y'])
            finally:store.pool.shutdown()

    def test_old_schedule_database_adds_language_without_changing_schedule(self):
        with tempfile.TemporaryDirectory() as temporary:
            with closing(sqlite3.connect(Path(temporary)/'dashboard.sqlite3')) as db, db:
                db.execute('CREATE TABLE schedules (id TEXT PRIMARY KEY, label TEXT, paths TEXT, interval_hours INTEGER, next_run INTEGER, enabled INTEGER)')
                db.execute('INSERT INTO schedules VALUES (?,?,?,?,?,?)',('existing','Finance','["finance"]',24,1234,0))
            store=Store(temporary,'cellwright')
            try:
                schedule=store.list('schedules')[0]
                self.assertEqual(schedule,{'id':'existing','label':'Finance','paths':'["finance"]','interval_hours':24,'next_run':1234,'enabled':0,'lang':'en'})
            finally:store.pool.shutdown()
            reopened=Store(temporary,'cellwright')
            try:self.assertEqual(reopened.list('schedules'),[schedule])
            finally:reopened.pool.shutdown()

    def test_schedule_language_survives_pause_resume_and_drives_due_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'cellwright')
            try:
                identifier=store.schedule({'paths':['finance'],'interval_hours':1,'lang':'de'})
                original=store.list('schedules')[0]
                value={'id':identifier,'paths':['finance'],'interval_hours':1,'enabled':False}
                store.schedule(value)
                self.assertEqual(store.list('schedules')[0]['lang'],'de')
                self.assertEqual(store.due(original['next_run']),0)
                store.schedule(dict(value,enabled=True))
                submitted=[]
                with patch.object(store,'submit',side_effect=lambda *args:submitted.append(args)):
                    self.assertEqual(store.due(original['next_run']),1)
                self.assertEqual(submitted[0][3],{'source':False,'lang':'de'})
                self.assertEqual(store.list('schedules')[0]['next_run'],original['next_run']+3600)
                store.schedule(dict(value,lang='fr'))
                self.assertEqual(store.list('schedules')[0]['lang'],'fr')
                for language in ('es','',None,[],{}):
                    with self.assertRaisesRegex(ValueError,'Invalid language'):
                        store.schedule(dict(value,lang=language))
                    with self.assertRaisesRegex(ValueError,'Invalid language'):
                        store.submit('scan','invalid',['finance'],{'lang':language})
                self.assertEqual(store.list('jobs'),[])
                self.assertEqual(store.list('schedules')[0]['lang'],'fr')
            finally:store.pool.shutdown()

    def test_localized_presentations_keep_machine_values_and_source_data(self):
        setup={'checks':[{'id':'scanner','label':'Workbook scanner','available':False,'needed_for':'Inventory','action':'Use the full Cellwright archive, or build the scanner with cargo build --locked --release.'}],'demo':'private.xlsm','first_scan_ready':False}
        localized=setup_response(setup,'fr')
        self.assertEqual(localized['checks'][0]['label'],'Analyseur de classeurs')
        self.assertEqual(setup['checks'][0]['label'],'Workbook scanner')
        self.assertEqual(localized['demo'],setup['demo'])
        self.assertIn('cargo build --locked --release',localized['checks'][0]['action'])
        finding={'rule_id':'CUSTOM-1','verdict':'unknown','messages':['Custom skipped part','Partie personnalisée ignorée','Benutzerdefinierter Teil übersprungen']}
        report={'target':'basic','modules':[{'name':'PrivateCustomer','kind':'standard','todos':[{'reason':'Custom source warning','source':'Private source text'}],'rewrites':[]}], 'workbook_findings':[finding], 'buttons':{'records':[{'status':'rewritten','sheet':'Private sheet','control':'CustomerControl'}]}}
        report['checklist']=checklist(report)
        original=copy.deepcopy(report)
        localized=conversion_response(copy.deepcopy(report),'de')
        self.assertEqual(localized['workbook_findings'],original['workbook_findings'])
        self.assertEqual(localized['modules'],original['modules'])
        self.assertEqual(localized['checklist']['coverage_status'],'unknown')
        self.assertEqual(localized['checklist']['items'][-1]['reason'],finding['messages'][2])
        self.assertIn('Prüfen',localized['checklist']['items'][0]['next_action'])
        self.assertEqual(localized['checklist']['items'][1]['reason'],'Custom source warning')
        self.assertEqual(localized['buttons']['records'][0]['control'],'CustomerControl')
        summary=handoff_response(handoff(report),'de')
        self.assertEqual(summary['purpose'],'Optionale Migrationsprüfung')
        self.assertEqual(summary['modules'][0]['label'],'Modul 1')
        self.assertEqual(summary['rule_counts'],{'CUSTOM-1':1})
        self.assertEqual(summary['coverage_status'],'unknown')
        self.assertNotIn('PrivateCustomer',json.dumps(summary))
        self.assertEqual(handoff_response(handoff(report,include_identifiers=True),'de',True)['modules'][0]['label'],'PrivateCustomer')
        self.assertEqual(translate('Unexpected technical details: 42','fr'),'Unexpected technical details: 42')

    def test_http_language_validation_and_localized_responses(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'cellwright');server=Server(('127.0.0.1',0),store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://'+server.authority
            def request(path,language='fr',body=None,authorized=True):
                headers={'X-Cellwright-Language':language,'Content-Type':'application/json'}
                if authorized:headers['X-Cellwright-Token']=server.token
                return urllib.request.urlopen(urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5)
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/state',authorized=False)
                self.assertEqual(error.exception.code,403)
                self.assertEqual(json.load(error.exception)['error'],'Jeton de session non valide');error.exception.close()
                with request('/api/state') as response:
                    self.assertEqual(json.load(response)['setup']['checks'][0]['label'],'Analyseur de classeurs')
                self.assertEqual(server.setup['checks'][0]['label'],'Workbook scanner')
                with request('/api/setup','de') as response:
                    self.assertEqual(json.load(response)['checks'][0]['label'],'Arbeitsmappen-Scanner')
                with request('/api/state','invalid') as response:
                    self.assertEqual(json.load(response)['setup']['checks'][0]['label'],'Workbook scanner')
                for path in ('/api/scans','/api/schedules'):
                    with self.assertRaises(urllib.error.HTTPError) as error:request(path,body={'paths':['finance'],'lang':'es'})
                    self.assertEqual(error.exception.code,400)
                    self.assertEqual(json.load(error.exception)['error'],'Langue non valide');error.exception.close()
                submitted=[]
                with patch.object(store,'submit',side_effect=lambda *args:submitted.append(args) or 'scan'):
                    for language in ('en','fr','de'):
                        with request('/api/scans',body={'paths':['finance'],'lang':language}) as response:self.assertEqual(json.load(response)['id'],'scan')
                self.assertEqual([args[3]['lang'] for args in submitted],['en','fr','de'])
                with request('/api/schedules',body={'paths':['finance'],'lang':'fr'}) as response:identifier=json.load(response)['id']
                self.assertEqual(store.list('schedules')[0]['id'],identifier)
                self.assertEqual(store.list('schedules')[0]['lang'],'fr')
                identifier='conversion'
                directory=Path(temporary)/identifier;directory.mkdir()
                report={'target':'basic','modules':[{'name':'Module1','kind':'standard','todos':[{'rule_id':'CUSTOM-2','reason':'Custom scanner warning'}],'rewrites':[],'procedures':[{'name':'Calculate','parameters':'','kind':'sub'}]}]}
                report['checklist']=checklist(report)
                serialized=json.dumps(report)
                (directory/'conversion.json').write_text(serialized,encoding='utf-8')
                inventory={'workbooks':[{'modules':[{'findings':[{'messages':['Custom scanner warning','Avertissement personnalisé','Benutzerdefinierte Warnung']}]}]}]}
                (directory/'inventory').mkdir()
                (directory/'inventory/scan.json').write_text(json.dumps(inventory),encoding='utf-8')
                with store.connect() as db:
                    db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',(identifier,'convert','Private source label','completed',0,0,json.dumps('private.xlsm'),json.dumps({'target':'basic'}),None,None))
                with request('/api/jobs/'+identifier) as response:
                    localized=json.load(response)
                    self.assertEqual(localized['checklist']['items'][1]['reason'],'Avertissement personnalisé')
                    self.assertEqual(localized['modules'][0]['todos'][0]['reason'],'Avertissement personnalisé')
                self.assertEqual((directory/'conversion.json').read_text(encoding='utf-8'),serialized)
                with request('/api/handoff','de',{'conversion_id':identifier}) as response:
                    summary=json.load(response)
                    self.assertEqual(summary['purpose'],'Optionale Migrationsprüfung')
                    self.assertEqual(summary['modules'][0]['label'],'Modul 1')
                    self.assertNotIn('Private source label',json.dumps(summary))
            finally:server.shutdown();server.server_close();store.pool.shutdown();thread.join()

    def test_http_auth_origin_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'cellwright');server=Server(('127.0.0.1',0),store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://'+server.authority
            def request(path,headers=None,body=None):
                return urllib.request.urlopen(urllib.request.Request(url+path,data=body,headers=headers or {}),timeout=5)
            try:
                with request('/') as response:self.assertIn(server.token,response.read().decode())
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/state')
                self.assertEqual(error.exception.code,403)
                error.exception.close()
                with request('/api/state',{'X-Cellwright-Token':server.token}) as response:self.assertEqual(json.load(response)['jobs'],[])
                local={'Host':f'localhost:{server.server_port}','Origin':f'http://localhost:{server.server_port}','X-Cellwright-Token':server.token}
                with request('/api/state',local) as response:self.assertFalse(json.load(response)['allow_execution'])
                for host in ('attacker.invalid',f'127.0.0.1.attacker.invalid:{server.server_port}'):
                    with self.assertRaises(urllib.error.HTTPError) as error:request('/',{'Host':host})
                    self.assertEqual(error.exception.code,403);error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/state',dict(local,Origin='http://'+server.authority))
                self.assertEqual(error.exception.code,403);error.exception.close()
                headers={'X-Cellwright-Token':server.token,'Content-Type':'application/json'}
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/verifications',headers,b'{"allow_execution":true}')
                self.assertEqual(error.exception.code,403);error.exception.close()
                with self.assertRaises(PermissionError):store.submit('verify','test',{}, {})
                self.assertEqual(store.list('jobs'),[])
                headers={'X-Cellwright-Token':server.token,'Content-Type':'application/json','Origin':'https://attacker.invalid'}
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/assignments',headers,b'{}')
                self.assertEqual(error.exception.code,403)
                error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:request('/files/../../server.py',{'Cookie':'mf_session='+server.token})
                error.exception.close()
            finally:server.shutdown();server.server_close();store.pool.shutdown();thread.join()

    def test_scan_option_like_path_is_positional(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'cellwright')
            try:
                def scan(command, **kwargs):
                    self.assertEqual(command[-3:],['--','--no-source.xlsm','-finance'])
                    self.assertIn('--no-source',command[:-3])
                    output=Path(command[command.index('--out')+1]);output.mkdir()
                    (output/'scan.json').write_text(json.dumps({'workbooks':[],'unique_modules':0,'estimated_hours_low':0,'estimated_hours_high':0,'source_included':False}))
                    from subprocess import CompletedProcess
                    return CompletedProcess(command,0)
                with patch('dashboard.server.subprocess.run',side_effect=scan):
                    identifier=store.submit('scan','dash paths',['--no-source.xlsm','-finance'],{})
                    store.pool.shutdown(wait=True)
                self.assertEqual(store.job(identifier)['state'],'completed')
            finally:store.pool.shutdown()

    def test_linux_verification_passes_saved_golden_and_requires_consent(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'cellwright',allow_execution=True);server=Server(('127.0.0.1',0),store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            original=Path(temporary)/'original.xlsm';original.write_bytes(b'original')
            golden=Path(temporary)/'saved-excel.json';golden.write_text('{"sheets":{}}')
            identifier='conversion'
            with store.connect() as db:
                db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',(identifier,'convert','owned case','completed',0,0,json.dumps(str(original)),json.dumps({'target':'basic'}),None,None))
            value={'conversion_id':identifier,'macro':'Arithmetic.Calculate','inputs':[2],'ranges':{'Data':['A1']},'allow_execution':True}
            url='http://'+server.authority+'/api/verifications'
            def request(value):
                return urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(value).encode(),headers={'X-Cellwright-Token':server.token,'Content-Type':'application/json'}),timeout=5)
            try:
                with patch.object(server,'requires_golden',True):
                    with self.assertRaises(urllib.error.HTTPError) as error:request(value)
                    self.assertEqual(error.exception.code,400);self.assertIn(b'saved Excel',error.exception.read());error.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as error:request(dict(value,golden=str(golden),allow_execution=False))
                    self.assertEqual(error.exception.code,403);error.exception.close()
                    submitted=[]
                    with patch.object(store,'submit',side_effect=lambda *args:submitted.append(args) or 'proof'):
                        with request(dict(value,golden=str(golden))) as response:self.assertEqual(json.load(response)['id'],'proof')
                    self.assertEqual(submitted[0][2]['golden'],str(golden.resolve()))
                    self.assertEqual(submitted[0][2]['original']['inputs'],[2])
                def verified(case,destination,allow_execution):
                    self.assertTrue(allow_execution);self.assertEqual(case['golden'],str(golden.resolve()))
                    return {'passed':True,'cells_checked':1,'differences':[]}
                with patch('migration.verify.verify',side_effect=verified):
                    proof=store.submit(*submitted[0]);store.pool.shutdown(wait=True)
                self.assertEqual(store.job(proof)['state'],'completed')
            finally:server.shutdown();server.server_close();store.pool.shutdown();thread.join()


if __name__=='__main__':unittest.main()
