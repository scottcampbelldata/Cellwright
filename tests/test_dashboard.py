# SPDX-License-Identifier: EUPL-1.2
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from pathlib import Path

from dashboard.server import Server, Store, validate_paths


class DashboardTests(unittest.TestCase):
    def test_schedule_and_assignments_persist(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary, 'macroferry')
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
                self.assertEqual(store.due(due),0)
                with self.assertRaises(ValueError):store.assignment({'path':'x','state':'invented'})
                with self.assertRaises(ValueError):validate_paths(['x\0y'])
            finally:store.pool.shutdown()

    def test_http_auth_origin_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'macroferry');server=Server(('127.0.0.1',0),store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://'+server.authority
            def request(path,headers=None,body=None):
                return urllib.request.urlopen(urllib.request.Request(url+path,data=body,headers=headers or {}),timeout=5)
            try:
                with request('/') as response:self.assertIn(server.token,response.read().decode())
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/state')
                self.assertEqual(error.exception.code,403)
                error.exception.close()
                with request('/api/state',{'X-MacroFerry-Token':server.token}) as response:self.assertEqual(json.load(response)['jobs'],[])
                local={'Host':f'localhost:{server.server_port}','Origin':f'http://localhost:{server.server_port}','X-MacroFerry-Token':server.token}
                with request('/api/state',local) as response:self.assertFalse(json.load(response)['allow_execution'])
                for host in ('attacker.invalid',f'127.0.0.1.attacker.invalid:{server.server_port}'):
                    with self.assertRaises(urllib.error.HTTPError) as error:request('/',{'Host':host})
                    self.assertEqual(error.exception.code,403);error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/state',dict(local,Origin='http://'+server.authority))
                self.assertEqual(error.exception.code,403);error.exception.close()
                headers={'X-MacroFerry-Token':server.token,'Content-Type':'application/json'}
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/verifications',headers,b'{"allow_execution":true}')
                self.assertEqual(error.exception.code,403);error.exception.close()
                with self.assertRaises(PermissionError):store.submit('verify','test',{}, {})
                self.assertEqual(store.list('jobs'),[])
                headers={'X-MacroFerry-Token':server.token,'Content-Type':'application/json','Origin':'https://attacker.invalid'}
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/assignments',headers,b'{}')
                self.assertEqual(error.exception.code,403)
                error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:request('/files/../../server.py',{'Cookie':'mf_session='+server.token})
                error.exception.close()
            finally:server.shutdown();server.server_close();store.pool.shutdown();thread.join()

    def test_scan_option_like_path_is_positional(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary,'macroferry')
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
            store=Store(temporary,'macroferry',allow_execution=True);server=Server(('127.0.0.1',0),store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            original=Path(temporary)/'original.xlsm';original.write_bytes(b'original')
            golden=Path(temporary)/'saved-excel.json';golden.write_text('{"sheets":{}}')
            identifier='conversion'
            with store.connect() as db:
                db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',(identifier,'convert','owned case','completed',0,0,json.dumps(str(original)),json.dumps({'target':'basic'}),None,None))
            value={'conversion_id':identifier,'macro':'Arithmetic.Calculate','inputs':[2],'ranges':{'Data':['A1']},'allow_execution':True}
            url='http://'+server.authority+'/api/verifications'
            def request(value):
                return urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(value).encode(),headers={'X-MacroFerry-Token':server.token,'Content-Type':'application/json'}),timeout=5)
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
