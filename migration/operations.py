# SPDX-License-Identifier: EUPL-1.2
"""Explicit spreadsheet operations shared by the two conversion front ends."""
import re
from migration import vba

CONSTANTS = {'xlascending':1,'xldescending':2,'xlyes':1,'xlno':2}


def call(text):
    text=re.sub(r'(?i)^call\s+','',text)
    match=re.fullmatch(r'(.+)\.(clearcontents|clear|copy|sort|autofilter)(?:\s*\((.*)\)|\s+(.+))?',text,re.I)
    if not match:return None
    root=vba.expression(match[1]);method=match[2].lower()
    raw=match[3] if match[3] is not None else match[4] or ''
    args=[];start=0;depth=0;quoted=False
    for index,ch in enumerate(raw+','):
        if ch=='"':quoted=not quoted
        if not quoted:depth+=(ch=='(')-(ch==')')
        if ch==',' and not depth and not quoted:
            value=raw[start:index].strip();start=index+1
            if value:args.append(value)
            elif raw:raise vba.Unsupported('Omitted operation arguments need manual migration')
    values={}
    order={'copy':['destination'],'sort':['key1','order1','header'],'autofilter':['field','criteria1']}.get(method,[])
    for index,arg in enumerate(args):
        pair=arg.split(':=',1)
        if method=='sort' and len(pair)==1 and index>1:raise vba.Unsupported('Sort Header must be named explicitly')
        key=pair[0].strip().lower() if len(pair)==2 else order[index] if index<len(order) else None
        if key not in order or key in values:raise vba.Unsupported('Unsupported or duplicate '+method+' argument')
        values[key]=vba.expression(pair[-1])
    if set(values)!=set(order):raise vba.Unsupported(method+' requires explicit '+', '.join(order))
    if method=='sort':
        for key in ('order1','header'):
            node=values[key]
            if node.get('name')=='xlguess' or node['kind']=='number' and node['value'] not in ('1','2'):
                raise vba.Unsupported('Sorting requires explicit ascending/descending order and yes/no header')
    return root,method,values


def basic(text, ranges=()):
    parsed=call(text)
    if not parsed:return None
    from migration.convert import uno_cell,basic_expression
    root,method,args=parsed
    target=uno_cell(root,True,ranges)
    if method in ('clear','clearcontents'):return 'MFClear '+target+', '+('887' if method=='clear' else '23')
    if method=='copy':return 'MFCopy '+target+', '+uno_cell(args['destination'],True)
    def scalar(node):
        return str(CONSTANTS[node['name']]) if node.get('name') in CONSTANTS else basic_expression(node)
    if method=='sort':return 'MFSort '+target+', '+uno_cell(args['key1'],True)+', '+scalar(args['order1'])+', '+scalar(args['header'])
    return 'MFFilter '+target+', '+scalar(args['field'])+', '+scalar(args['criteria1'])


def python(text):
    parsed=call(text)
    if not parsed:return None
    root,method,args=parsed
    if method=='copy':return vba.emit(root)+'.copy('+vba.emit(args['destination'])+')'
    def scalar(node):return str(CONSTANTS[node['name']]) if node.get('name') in CONSTANTS else vba.emit(node)
    order={'sort':['key1','order1','header'],'autofilter':['field','criteria1']}.get(method,[])
    return vba.emit(root)+'.'+method+'('+', '.join(scalar(args[key]) for key in order)+')'


def rename(text, created=()):
    pair=vba.assignment(text)
    if not pair:return None
    lhs,rhs=pair
    if lhs['kind']!='member' or lhs['name']!='name':return None
    target=lhs['object']
    from migration.convert import basic_expression
    if target['kind']=='call' and target['object'].get('name') in ('worksheets','sheets') and len(target['args'])==1:
        obj='ThisComponent.Sheets.getByName('+basic_expression(target['args'][0])+')'
    elif target['kind']=='member' and target['name']=='add' and target['object'].get('name') in ('worksheets','sheets'):obj='MFAddSheet()'
    elif target['kind']=='identifier' and target['name'] in created:obj=target['name']
    else:return None
    return 'MFRenameSheet '+obj+', '+basic_expression(rhs)


def helpers():
    return ''''
Sub MFRenameSheet(sheet As Object, name As String)
    Dim char As String, i As Long, other As Object
    If Len(name) < 1 Or Len(name) > 31 Or Left(name, 1) = "'" Or Right(name, 1) = "'" Then Err.Raise 5, "Cellwright", "Invalid sheet name"
    For i = 1 To Len("[]:*?/\\")
        char = Mid("[]:*?/\\", i, 1)
        If InStr(name, char) Then Err.Raise 5, "Cellwright", "Invalid sheet name"
    Next i
    For Each other In ThisComponent.Sheets
        If LCase(other.Name) = LCase(name) And other.Name <> sheet.Name Then Err.Raise 5, "Cellwright", "Sheet name already exists"
    Next other
    sheet.Name = name
End Sub
Sub MFRangeBound(target As Object)
    Dim bounds
    bounds = target.getRangeAddress()
    If (bounds.EndRow - bounds.StartRow + 1) * (bounds.EndColumn - bounds.StartColumn + 1) > 100000 Then Err.Raise 5, "Cellwright", "Range exceeds 100,000 cells"
End Sub
Sub MFClear(target As Object, flags As Long)
    MFRangeBound target
    target.clearContents(flags)
End Sub
Sub MFCopy(source As Object, destination As Object)
    Dim bounds, endpoint
    MFRangeBound source
    bounds = source.getRangeAddress()
    endpoint = destination.getRangeAddress()
    If endpoint.StartRow + bounds.EndRow - bounds.StartRow > 1048575 Or endpoint.StartColumn + bounds.EndColumn - bounds.StartColumn > 16383 Then Err.Raise 5, "Cellwright", "Copy exceeds sheet bounds"
    destination.getSpreadsheet().copyRange(destination.getCellByPosition(0, 0).getCellAddress(), bounds)
End Sub
Sub MFSort(target As Object, key As Object, ordering As Integer, header As Integer)
    Dim bounds, field, props(2) As New com.sun.star.beans.PropertyValue
    MFRangeBound target
    bounds = target.getRangeAddress()
    field = key.getRangeAddress()
    If field.Sheet <> bounds.Sheet Or field.StartColumn < bounds.StartColumn Or field.EndColumn > bounds.EndColumn Or field.StartColumn <> field.EndColumn Then Err.Raise 5, "Cellwright", "Sort key must be one column in the target"
    If (ordering <> 1 And ordering <> 2) Or (header <> 1 And header <> 2) Then Err.Raise 5, "Cellwright", "Explicit ascending/descending and yes/no header required"
    Dim keys(0) As New com.sun.star.table.TableSortField
    keys(0).Field = field.StartColumn - bounds.StartColumn
    keys(0).IsAscending = (ordering = 1)
    keys(0).FieldType = com.sun.star.table.TableSortFieldType.NUMERIC
    props(0).Name = "SortFields": props(0).Value = keys()
    props(1).Name = "ContainsHeader": props(1).Value = (header = 1)
    props(2).Name = "IsSortColumns": props(2).Value = False
    Dim row As Long, cell As Object
    For row = IIf(header = 1, 1, 0) To bounds.EndRow - bounds.StartRow
        cell = target.getCellByPosition(keys(0).Field, row)
        If cell.getType() <> 1 Then Err.Raise 5, "Cellwright", "Only numeric constant sort keys supported"
    Next row
    target.sort(props())
End Sub
Sub MFFilter(target As Object, field As Long, criteria As Variant)
    Dim bounds, descriptor, filters(0) As New com.sun.star.sheet.TableFilterField
    MFRangeBound target
    bounds = target.getRangeAddress()
    If field < 1 Or field > bounds.EndColumn - bounds.StartColumn + 1 Then Err.Raise 5, "Cellwright", "Invalid filter field"
    If VarType(criteria) = 8 Then
        If InStr(criteria, "*") Or InStr(criteria, "?") Or InStr(criteria, "~") Or Left(criteria, 1) = "<" Or Left(criteria, 1) = ">" Or Left(criteria, 1) = "=" Then Err.Raise 5, "Cellwright", "Only literal equality filters supported"
        filters(0).IsNumeric = False: filters(0).StringValue = criteria
    Else
        filters(0).IsNumeric = True: filters(0).NumericValue = criteria
    End If
    filters(0).Field = field - 1
    filters(0).Operator = com.sun.star.sheet.FilterOperator.EQUAL
    descriptor = target.createFilterDescriptor(True)
    descriptor.ContainsHeader = True
    descriptor.IsCaseSensitive = False
    descriptor.UseRegularExpressions = False
    descriptor.setFilterFields(filters())
    target.filter(descriptor)
End Sub
Function MFAddSheet() As Object
    Dim name As String, index As Long
    index = 1
    Do
        name = "Sheet" & index
        index = index + 1
    Loop While ThisComponent.Sheets.hasByName(name)
    ThisComponent.Sheets.insertNewByName(name, ThisComponent.Sheets.Count)
    MFAddSheet = ThisComponent.Sheets.getByName(name)
    ThisComponent.CurrentController.setActiveSheet(MFAddSheet)
End Function
'''
