# SPDX-License-Identifier: EUPL-1.2
"""Allowlisted M-to-pandas execution; no network providers or arbitrary eval."""
import functools
import json
from pathlib import Path

from migration.m import Parser, inventory

SUPPORTED_FUNCTIONS=frozenset('File.Contents Csv.Document Table.PromoteHeaders Table.TransformColumnTypes Table.SelectRows Table.Group Table.NestedJoin Table.ExpandTableColumn Table.Pivot Table.AddColumn Table.SelectColumns Table.RemoveColumns Table.RenameColumns Table.Distinct Table.Sort Table.FirstN Table.Skip Table.RowCount Table.Combine Table.FromRecords Table.FromRows List.Sum List.Average List.Min List.Max List.Count List.Distinct Text.Upper Text.Lower Text.Trim Text.Contains Text.StartsWith Number.Round Number.Abs'.split())

def functions(data_root):
    import pandas as pd
    root=Path(data_root).resolve()
    def file_contents(path):
        file=(root/path).resolve()
        if not file.is_relative_to(root): raise PermissionError("M file source is outside --data-root")
        if file.stat().st_size > 128*1024*1024: raise ValueError("M file source exceeds 128 MiB")
        return file.read_bytes()
    def csv_document(content, options=None):
        import io
        options=options or {}
        if options.get("Encoding",65001) != 65001: raise NotImplementedError("Only UTF-8 CSV is supported")
        frame=pd.read_csv(io.BytesIO(content),header=None,sep=options.get("Delimiter",","),dtype=str,keep_default_na=False)
        frame.columns=["Column"+str(index+1) for index in range(len(frame.columns))]
        return frame
    def promote(table, options=None):
        if table.empty: return table.copy()
        result=table.iloc[1:].copy();result.columns=table.iloc[0].tolist();return result.reset_index(drop=True)
    def transform_types(table, types, culture=None):
        if culture not in (None,"en-US","en-GB"): raise NotImplementedError("Locale-specific M coercion requires review")
        result=table.copy()
        for column,typ in types:
            if typ in ("type:number","type:int64","Int64.Type"): result[column]=pd.to_numeric(result[column],errors="raise")
            elif typ=="type:text": result[column]=result[column].astype(str)
            elif typ in ("type:date","type:datetime"): result[column]=pd.to_datetime(result[column],errors="raise")
            else: raise NotImplementedError("Unsupported M type "+str(typ))
        return result
    def select_rows(table,predicate): return table.loc[predicate(table)].copy().reset_index(drop=True)
    def group(table,keys,aggregations):
        keys=[keys] if isinstance(keys,str) else keys
        rows=[]
        for key,part in table.groupby(keys,dropna=False,sort=False):
            key=key if isinstance(key,tuple) else (key,)
            row=dict(zip(keys,key))
            for aggregate in aggregations: row[aggregate[0]]=aggregate[1](part)
            rows.append(row)
        return pd.DataFrame(rows,columns=keys+[aggregate[0] for aggregate in aggregations])
    def nested_join(left,left_keys,right,right_keys,name,kind="JoinKind.LeftOuter"):
        if kind not in ("JoinKind.LeftOuter","JoinKind.Inner"): raise NotImplementedError("Only left and inner nested joins are supported")
        if not left_keys or len(left_keys)!=len(right_keys):raise ValueError("Nested join requires matching, nonempty key lists")
        result=left.copy();nested=[];keep=[]
        for index,row in left.iterrows():
            mask=pd.Series(True,index=right.index)
            for lkey,rkey in zip(left_keys,right_keys): mask &= right[rkey].isna() if pd.isna(row[lkey]) else right[rkey].eq(row[lkey])
            matches=right.loc[mask].copy();nested.append(matches);keep.append(not matches.empty)
        result[name]=nested
        return result if kind=="JoinKind.LeftOuter" else result.loc[keep].reset_index(drop=True)
    def expand(table,name,columns,new_names=None):
        new_names=new_names or columns
        if len(columns)!=len(new_names): raise ValueError("Expand column count differs")
        rows=[]
        for _,row in table.iterrows():
            nested=row[name]
            for record in nested.to_dict("records") if not nested.empty else [dict.fromkeys(columns)]:
                output=row.drop(labels=[name]).to_dict();output.update({new:record.get(old) for old,new in zip(columns,new_names)});rows.append(output)
        return pd.DataFrame(rows)
    def pivot(table,values,attribute,value,aggregate=None):
        keys=[column for column in table.columns if column not in (attribute,value)]
        if not keys: raise NotImplementedError("Pivot requires at least one retained key column")
        if aggregate is None:
            result=table.pivot(index=keys,columns=attribute,values=value)
        else:
            result=table.pivot_table(index=keys,columns=attribute,values=value,aggfunc=lambda series:aggregate(series),dropna=False)
        return result.reindex(columns=values).reset_index()
    def add_column(table,name,fn,typ=None):
        result=table.copy();result[name]=table.apply(fn,axis=1);return result
    return {
        "File.Contents":file_contents,"Csv.Document":csv_document,"Table.PromoteHeaders":promote,
        "Table.TransformColumnTypes":transform_types,"Table.SelectRows":select_rows,"Table.Group":group,
        "Table.NestedJoin":nested_join,"Table.ExpandTableColumn":expand,"Table.Pivot":pivot,"Table.AddColumn":add_column,
        "Table.SelectColumns":lambda table,columns:table[columns].copy(),
        "Table.RemoveColumns":lambda table,columns:table.drop(columns=columns),
        "Table.RenameColumns":lambda table,pairs:table.rename(columns=dict(pairs)),
        "Table.Distinct":lambda table,columns=None:table.drop_duplicates(subset=columns).reset_index(drop=True),
        "Table.Sort":lambda table,order:table.sort_values([item[0] for item in order],ascending=[item[1]=="Order.Ascending" for item in order],kind="stable").reset_index(drop=True),
        "Table.FirstN":lambda table,n:table.head(n).copy(),"Table.Skip":lambda table,n:table.iloc[n:].copy(),
        "Table.RowCount":len,"Table.Combine":lambda tables:pd.concat(tables,ignore_index=True),
        "Table.FromRecords":lambda records:pd.DataFrame(records),
        "Table.FromRows":lambda rows,columns:pd.DataFrame(rows,columns=columns),
        "List.Sum":lambda values:values.sum() if hasattr(values,"sum") else sum(v for v in values if v is not None),
        "List.Average":lambda values:values.mean() if hasattr(values,"mean") else sum(values)/len(values),
        "List.Min":lambda values:values.min() if hasattr(values,"min") else min(values),
        "List.Max":lambda values:values.max() if hasattr(values,"max") else max(values),
        "List.Count":len,"List.Distinct":lambda values:list(dict.fromkeys(values)),
        "Text.Upper":lambda value:value.upper(),"Text.Lower":lambda value:value.lower(),"Text.Trim":lambda value:value.strip(),
        "Text.Contains":lambda value,part:part in value,"Text.StartsWith":lambda value,part:value.startswith(part),
        "Number.Round":round,"Number.Abs":abs,
    }


def evaluate(node, environment, allowed, depth=0):
    if depth>128: raise ValueError("M evaluation nesting limit exceeded")
    def run(value,env=environment): return evaluate(value,env,allowed,depth+1)
    kind=node["kind"]
    if kind=="literal":return node["value"]
    if kind=="identifier":
        name=node["name"]
        if name in environment: return environment[name]() if isinstance(environment[name],Lazy) else environment[name]
        if name in allowed:return allowed[name]
        if name in ("Int64.Type","QuoteStyle.Csv","JoinKind.LeftOuter","JoinKind.Inner","Order.Ascending","Order.Descending"):return name
        raise NotImplementedError("Unsupported M identifier/provider: "+name)
    if kind=="let":
        local=dict(environment)
        for name,value in node["bindings"]:local[name]=Lazy(lambda value=value:run(value,local))
        return run(node["body"],local)
    if kind=="lambda":return lambda value:run(node["body"],dict(environment,_=value))
    if kind=="list":return [run(value) for value in node["values"]]
    if kind=="record":return {name:run(value) for name,value in node["pairs"]}
    if kind=="field":return run(node["object"])[node["name"]]
    if kind=="call":return run(node["function"])(*[run(value) for value in node["args"]])
    if kind=="unary":
        value=run(node["value"])
        return (not value if isinstance(value,bool) else ~value) if node["op"]=="not" else -value if node["op"]=="-" else +value
    if kind=="binary":
        import operator
        left,right=run(node["left"]),run(node["right"])
        operations={"=":operator.eq,"<>":operator.ne,"<":operator.lt,">":operator.gt,"<=":operator.le,">=":operator.ge,"+":operator.add,"-":operator.sub,"*":operator.mul,"/":operator.truediv,"&":operator.add,"and":operator.and_,"or":operator.or_}
        return operations[node["op"]](left,right)
    raise NotImplementedError("Unsupported M syntax "+kind)


class Lazy:
    def __init__(self, fn):self.fn,self.busy,self.ready,self.value=fn,False,False,None
    def __call__(self):
        if self.ready:return self.value
        if self.busy:raise ValueError("Cyclic M query reference")
        self.busy=True
        try:self.value=self.fn();self.ready=True;return self.value
        finally:self.busy=False


def run(queries, query, data_root):
    allowed=functions(data_root);environment={}
    for name,node in queries.items():environment[name]=Lazy(lambda node=node:evaluate(node,environment,allowed))
    if query not in environment:raise ValueError("Query not found: "+query)
    return environment[query]()


def convert(source_path, destination):
    source_path,destination=Path(source_path),Path(destination)
    if destination.exists() and any(destination.iterdir()):raise FileExistsError("M conversion destination must be new or empty")
    source=source_path.read_text(encoding="utf-8-sig");queries=Parser(source).section()
    if not queries:raise ValueError("No M queries found")
    destination.mkdir(parents=True,exist_ok=True)
    (destination/"original.m").write_text(source,encoding="utf-8")
    (destination/"query.json").write_text(json.dumps(queries,indent=2),encoding="utf-8")
    details={name:inventory(node) for name,node in queries.items()}
    todos=[{'query':name,'reason':'Unsupported functions: '+', '.join(sorted(set(item['functions'])-SUPPORTED_FUNCTIONS))} for name,item in details.items() if set(item['functions'])-SUPPORTED_FUNCTIONS]
    report={"schema_version":"1","status":"candidate","verified":False,"queries":list(queries),"inventory":details,"todos":todos,"limitations":["Common table steps only; unsupported functions fail explicitly", "File sources must be within --data-root; network providers require manual migration"]}
    (destination/"conversion.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    generated='''# Generated by MacroFerry. Review original.m and compare tables before adoption.
import argparse, json
from pathlib import Path
from migration.m_runtime import run
parser=argparse.ArgumentParser()
parser.add_argument('--query', required=True)
parser.add_argument('--data-root', required=True)
parser.add_argument('--out', required=True)
args=parser.parse_args()
queries=json.loads(Path(__file__).with_name('query.json').read_text(encoding='utf-8'))
result=run(queries,args.query,args.data_root)
with open(args.out,'x',encoding='utf-8',newline='') as stream: result.to_csv(stream,index=False)
'''
    (destination/"query.py").write_text(generated,encoding="utf-8")
    package=destination/"migration";package.mkdir()
    for filename in ("__init__.py","m.py","m_runtime.py"):
        (package/filename).write_bytes((Path(__file__).parent/filename).read_bytes())
    (destination/"requirements.txt").write_text("pandas==3.0.6\n",encoding="utf-8")
    return report
