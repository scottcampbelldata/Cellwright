# SPDX-License-Identifier: EUPL-1.2
"""Keep additive inventory fields explicit in the published JSON Schema."""
import json
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'docs/scan.schema.json'
schema=json.loads(path.read_text(encoding='utf-8'))
strings={'type':'array','items':{'type':'string'}}
schema['$defs']['module']['properties']['api_usage']={'type':'array','items':{'type':'object','additionalProperties':False,'properties':{'object_type':{'type':'string'},'member':{'type':'string'},'line':{'type':'integer','minimum':1},'declared':{'type':'boolean'}},'required':['object_type','member','line','declared']}}
workbook=schema['$defs']['workbook']['properties']
workbook.update(owner={'type':['string','null']},code_page={'type':['integer','null'],'minimum':0,'maximum':65535},entry_points=strings,macro_assignments=strings,connections=strings)
workbook['forms']={'type':'array','items':{'type':'object','additionalProperties':False,'properties':{'name':{'type':'string'},'controls':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{'name':{'type':'string'},'control_type':{'type':'string'},'cached_index':{'type':'integer','minimum':0,'maximum':65535}},'required':['name','control_type','cached_index']}},'error':{'type':['string','null']},'layout':{'type':'string','contentEncoding':'base64'}},'required':['name','controls','error']}}
schema['$defs']['query']['properties'].update(names=strings,steps=strings,sources=strings)
schema['allOf'][0]['then']['properties']['workbooks']['items']['properties']['forms']={'items':{'not':{'required':['layout']}}}
path.write_text(json.dumps(schema,indent=2)+'\n',encoding='utf-8')
