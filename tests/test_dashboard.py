# SPDX-License-Identifier: EUPL-1.2
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
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
                headers={'X-MacroFerry-Token':server.token,'Content-Type':'application/json','Origin':'https://attacker.invalid'}
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/assignments',headers,b'{}')
                self.assertEqual(error.exception.code,403)
                error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:request('/files/../../server.py',{'Cookie':'mf_session='+server.token})
                error.exception.close()
            finally:server.shutdown();server.server_close();store.pool.shutdown();thread.join()


if __name__=='__main__':unittest.main()
