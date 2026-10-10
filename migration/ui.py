# SPDX-License-Identifier: EUPL-1.2
"""Bounded form candidates using imported dialog layouts and explicit control models."""
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from migration import vba

DLG = 'http://openoffice.org/2000/dialog'
SCRIPT = 'http://openoffice.org/2000/script'
ET.register_namespace('dlg', DLG)
ET.register_namespace('script', SCRIPT)
TAGS = {'CommandButton':'button', 'Label':'text', 'TextBox':'textfield', 'CheckBox':'checkbox', 'OptionButton':'radio', 'ListBox':'menulist', 'ComboBox':'combobox'}
PROPERTIES = {'CommandButton':{'caption':'Label'}, 'Label':{'caption':'Label'}, 'TextBox':{'value':'Text','text':'Text'}, 'CheckBox':{'value':'State','caption':'Label'}, 'OptionButton':{'value':'State','caption':'Label'}, 'ListBox':{'listindex':'SelectedItems'}, 'ComboBox':{'value':'Text','text':'Text'}}
EVENTS = {'CommandButton':{'click':('XActionListener','actionPerformed','on-performaction')}, 'TextBox':{'change':('XTextListener','textChanged','on-textchange')}, 'CheckBox':{'click':('XItemListener','itemStateChanged','on-itemstatechange')}, 'OptionButton':{'click':('XItemListener','itemStateChanged','on-itemstatechange')}, 'ListBox':{'change':('XItemListener','itemStateChanged','on-itemstatechange')}, 'ComboBox':{'change':('XTextListener','textChanged','on-textchange')}}
CLASSES = {'D7053240-CE69-11CD-A777-00DD01143C57':'CommandButton','8BD21D10-EC42-11CE-9E0D-00AA006002F3':'TextBox','8BD21D20-EC42-11CE-9E0D-00AA006002F3':'ListBox','8BD21D30-EC42-11CE-9E0D-00AA006002F3':'ComboBox','8BD21D40-EC42-11CE-9E0D-00AA006002F3':'CheckBox','8BD21D50-EC42-11CE-9E0D-00AA006002F3':'OptionButton','978C9E23-D4B0-11CE-BF2D-00AA003F40D0':'Label'}
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')


def inventory(workbook, filename):
    forms = [{**form, 'scope':'dialog', 'controls':form['controls']} for form in workbook.get('forms', [])]
    if zipfile.is_zipfile(filename):
        with zipfile.ZipFile(filename) as archive:
            expanded=0
            def read(name):
                nonlocal expanded
                entry=archive.getinfo(name)
                if entry.file_size>16*1024*1024 or expanded+entry.file_size>256*1024*1024:raise ValueError('Control metadata exceeds archive limits')
                with archive.open(entry) as stream:data=stream.read(16*1024*1024+1)
                if len(data)>16*1024*1024:raise ValueError('Control metadata exceeds part limit')
                expanded+=len(data)
                return data
            namespaces = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for info in archive.infolist():
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml', info.filename) or info.file_size > 16*1024*1024: continue
                root = ET.fromstring(read(info.filename))
                controls = root.findall('.//s:control', namespaces)
                if not controls: continue
                prop = root.find('s:sheetPr', namespaces)
                code = prop.get('codeName') if prop is not None else None
                relname = str(Path(info.filename).parent / '_rels' / (Path(info.filename).name+'.rels')).replace('\\','/')
                relationships = ET.fromstring(read(relname)) if relname in archive.namelist() else []
                targets = {r.get('Id'):r.get('Target') for r in relationships if r.get('TargetMode') != 'External'}
                items = []
                for control in controls:
                    target = targets.get(control.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'), '')
                    # shortcut: only worksheet-local ../activeX relationships are supported; nested/custom objects stay manual.
                    part = 'xl/activeX/'+target.split('/')[-1] if target.startswith('../activeX/') else target.lstrip('/')
                    if not part.startswith('xl/activeX/'):
                        continue
                    typ = 'CustomOrUnknown'
                    if part in archive.namelist():
                        entry = archive.getinfo(part)
                        if entry.file_size <= 16*1024*1024:
                            xml = ET.fromstring(read(entry.filename))
                            clsid = xml.get('{http://schemas.microsoft.com/office/2006/activeX}classid', xml.get('classid','')).strip('{}').upper()
                            typ = CLASSES.get(clsid, typ)
                    items.append({'name':control.get('name',''), 'control_type':typ})
                if items:forms.append({'name':code or '', 'scope':'sheet', 'controls':items, 'error':None if code else 'Missing worksheet code name'})
    return forms


def bindings(module, spec):
    controls = {c['name'].lower():c for c in spec['controls']}
    result = []
    for node in vba.syntax(module['source']):
        if node['kind'] != 'procedure': continue
        control, separator, event = node['name'].rpartition('_')
        if not separator or control not in controls:
            if node['name'].startswith(('userform_','worksheet_','workbook_')):
                result.append({'procedure':node['name'], 'status':'manual', 'reason':'Lifecycle and automatic events need manual migration'})
            continue
        item = controls[control]
        record = {'control':item['name'], 'procedure':node['name'], 'event':event, 'status':'manual'}
        mapping = EVENTS.get(item['control_type'],{}).get(event)
        if mapping and node['procedure_kind']=='sub' and not node['parameters'].strip():
            record.update(status='candidate', listener=mapping[0], method=mapping[1], xml_event=mapping[2])
        else:record['reason']='This control event or parameter signature needs manual migration'
        result.append(record)
    return result


def rewrite(source, module, specs):
    """Rewrite explicit form/control references; retain unsupported lines as TODOs."""
    known = {s['name'].lower():s for s in specs if NAME.fullmatch(s['name']) and not s.get('error')}
    current = known.get(module.lower())
    todos, rewrites, output = [], [], []
    shadowed=set()
    for node in vba.syntax(source):
        if node['kind']=='procedure':shadowed.update(vba.tokens(node['parameters']))
        elif re.match(r'(?i)^(?:dim|static|const|private|public)\b',node['source']):shadowed.update(vba.tokens(node['source']))
    def control(node):
        name = None
        if node['kind']=='identifier' and current:
            name, spec = node['name'], current
            if name in shadowed:raise vba.Unsupported('Control identifier is shadowed; use an explicit Me reference after review')
        elif node['kind']=='member' and node['object']['kind']=='identifier':
            owner = node['object']['name']
            if owner in shadowed and owner!='me':raise vba.Unsupported('Form identifier is shadowed')
            spec = current if owner=='me' else known.get(owner)
            name = node['name']
        else:return None
        if spec:
            item = next((c for c in spec['controls'] if c['name'].lower()==name),None)
            if item:
                if not NAME.fullmatch(item['name']) or item['control_type'] not in TAGS:raise vba.Unsupported('Custom control or invalid control name needs manual migration')
                return spec, item
        return None
    def expr(node):
        if node['kind']=='member':
            matched = control(node['object'])
            if matched:
                spec,item = matched
                prop = node['name']
                if prop not in PROPERTIES.get(item['control_type'],{}) and prop not in ('enabled','visible'):
                    raise vba.Unsupported('Control property '+prop+' needs manual migration')
                return 'MFUIGet('+object_expr(spec,item)+', "'+prop+'")'
        if control(node):raise vba.Unsupported('Default control properties require explicit Value or Text')
        kind=node['kind']
        if kind=='identifier' and (node['name']=='me' or node['name'] in known):raise vba.Unsupported('Dynamic form/control references need manual migration')
        if kind in ('literal','number','identifier'):
            from migration.convert import basic_expression
            return basic_expression(node)
        if kind=='member':return expr(node['object'])+'.'+node['name']
        if kind=='call':return expr(node['object'])+'('+', '.join(expr(a) for a in node['args'])+')'
        if kind=='unary':return '('+node['op']+' '+expr(node['value'])+')'
        if kind=='binary':return '('+expr(node['left'])+' '+node['op']+' '+expr(node['right'])+')'
        raise vba.Unsupported('Control expression needs manual migration')
    def object_expr(spec,item):
        return 'MFUIControl("'+spec['scope']+'", "'+spec['name']+'", "'+item['name']+'", "'+item['control_type']+'")'
    for number,line in enumerate(source.replace('\r\n','\n').replace('\r','\n').splitlines(),1):
        parts = list(vba.split_statements(line))
        if not parts:output.append(line);continue
        text = parts[0][1]
        words = set(vba.tokens(text))
        names = set(known) | {'me','userforms','controls'}
        if current:names.update(c['name'].lower() for c in current['controls'])
        if not words & names or re.match(r'(?i)^(attribute|option|(?:private |public )?(?:sub|function)|end (?:sub|function))\b',text):
            output.append(line);continue
        try:
            if len(parts)!=1:raise vba.Unsupported('Compound control statements need manual migration')
            show = re.fullmatch(r'(?i)(\w+)\.(show|hide)(?:\s*\(\s*\))?',text)
            unload = re.fullmatch(r'(?i)unload\s+(\w+)',text)
            if show or unload:
                owner = (show or unload)[1].lower()
                spec = current if owner=='me' else known.get(owner)
                if not spec or spec['scope']!='dialog':raise vba.Unsupported('Only explicit modal UserForms are supported')
                operation = show[2].lower() if show else 'unload'
                replacement = 'MFUI'+operation.title()+' "'+spec['name']+'"'
            else:
                pair = vba.assignment(text)
                if pair:
                    lhs,rhs = pair
                    matched = control(lhs['object']) if lhs['kind']=='member' else None
                    if matched:
                        spec,item = matched
                        prop=lhs['name']
                        if prop not in PROPERTIES.get(item['control_type'],{}) and prop not in ('enabled','visible'):raise vba.Unsupported('Control property '+prop+' needs manual migration')
                        replacement = 'MFUISet '+object_expr(spec,item)+', "'+prop+'", '+expr(rhs)
                    else:replacement = expr(lhs)+' = '+expr(rhs)
                elif text.lower().startswith('if ') and text.lower().endswith(' then'):
                    replacement = 'If '+expr(vba.expression(text[3:-5]))+' Then'
                else:raise vba.Unsupported('Control methods, dynamic Controls, With and lifecycle code need manual migration')
            output.append(replacement)
            rewrites.append({'line':number,'rule_id':'UI-CONTROL','before':line,'after':replacement})
        except vba.Unsupported as error:
            output.append(line)
            todos.append({'line':number,'rule_id':'UI-MANUAL','reason':str(error)})
    return {'source':'\n'.join(output)+'\n','todos':todos,'rewrites':rewrites}


def dialog_candidate(xml, spec, callbacks):
    if len(xml)>16*1024*1024 or b'<!ENTITY' in xml.upper():raise ValueError('Unsafe or oversized dialog XML')
    xml=re.sub(br'<!DOCTYPE[^>]*>',b'',xml)
    root=ET.fromstring(xml)
    if sum(1 for _ in root.iter())>20000:raise ValueError('Dialog XML exceeds 20,000 nodes')
    if root.tag!='{'+DLG+'}window':raise ValueError('Not a dialog window')
    for node in root.iter():
        if node is root or node.tag in {'{'+DLG+'}'+tag for tag in TAGS.values()}:
            for attribute in ('left','top','width','height'):
                value=node.get('{'+DLG+'}'+attribute,'')
                if not re.fullmatch(r'-?\d{1,5}',value) or (attribute in ('width','height') and int(value)<=0):
                    raise ValueError('Missing or invalid dialog geometry: '+attribute)
            if node is not root and not re.fullmatch(r'\d{1,5}',node.get('{'+DLG+'}tab-index','')):
                raise ValueError('Missing or invalid dialog tab index')
    records=[]
    for parent in root.iter():
        for child in list(parent):
            if child.tag.startswith('{'+SCRIPT+'}'):
                parent.remove(child)
                records.append({'status':'manual','reason':'Imported callback removed; only source-matched events can be rebound','control':parent.get('{'+DLG+'}id','')})
    for node in root.iter():
        for attribute in list(node.attrib):
            if attribute.split('}')[-1] in ('image-src','help-url','linked-cell','source-cell-range','control-implementation'):
                node.attrib.pop(attribute)
                records.append({'status':'manual','control':node.get('{'+DLG+'}id',''), 'reason':'External resource, data binding or custom implementation removed; restore it explicitly after review'})
    ids=[n.get('{'+DLG+'}id') for n in root.iter() if n.get('{'+DLG+'}id')]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate imported control names')
    nodes={n.get('{'+DLG+'}id'):n for n in root.iter() if n.get('{'+DLG+'}id')}
    if len(nodes)>10000:raise ValueError('Dialog exceeds 10,000 controls')
    layout_ok=not spec.get('error') and root.get('{'+DLG+'}id')==spec['name']
    for item in spec['controls']:
        node=nodes.get(item['name'])
        good=node is not None and node.tag=='{'+DLG+'}'+TAGS.get(item['control_type'],'unsupported')
        if not good:
            layout_ok=False
            records.append({'control':item['name'],'status':'manual','reason':'Unsupported or missing imported control; recreate it using the control recipe'})
    for entry in callbacks:
        record=dict(entry)
        records.append(record)
        node=nodes.get(entry.get('control'))
        if entry['status']=='candidate' and layout_ok and node is not None:
            uri='vnd.sun.star.script:Standard.'+spec['name']+'.'+entry['wrapper']+'?language=Basic&location=document'
            ET.SubElement(node,'{'+SCRIPT+'}event',{'{'+SCRIPT+'}event-name':entry['xml_event'],'{'+SCRIPT+'}macro-name':uri,'{'+SCRIPT+'}language':'Script'})
            record.update(status='rewritten',after=uri)
        elif entry['status']=='candidate':record.update(status='manual',reason='Form layout or module needs manual review before wiring events')
    return ET.tostring(root,encoding='unicode',xml_declaration=True), records, layout_ok


def migrate_dialogs(document, specs, uno):
    libraries=document.DialogLibraries
    originals={}
    for name in libraries.getElementNames():
        libraries.loadLibrary(name)
        lib=libraries.getByName(name)
        for form in lib.getElementNames():
            stream=lib.getByName(form).createInputStream();data=b''
            while True:
                count,chunk=stream.readBytes(None,65536)
                if not count:break
                data+=bytes(chunk)
                if len(data)>16*1024*1024:raise ValueError('Imported dialog exceeds limit')
            if form in originals:raise ValueError('Ambiguous imported dialog name')
            originals[form]=data
    for name in tuple(libraries.getElementNames()):libraries.removeLibrary(name)
    library=libraries.createLibrary('Standard')
    result=[]
    for spec in specs:
        if spec['scope']!='dialog':continue
        item={'name':spec['name'],'scope':'dialog','status':'manual','records':[], 'controls':len(spec['controls'])}
        result.append(item)
        try:
            if spec['name'] not in originals:raise ValueError('UserForm layout was not imported; use the manual form recipe')
            original=originals[spec['name']]
            xml,records,good=dialog_candidate(original,spec,spec.get('callbacks',[]))
            import unohelper
            from com.sun.star.io import XInputStreamProvider
            class Provider(unohelper.Base, XInputStreamProvider):
                def __init__(self, data): self.data = data
                def createInputStream(self):
                    context = uno.getComponentContext()
                    value = context.ServiceManager.createInstanceWithContext('com.sun.star.io.SequenceInputStream', context)
                    value.initialize((uno.ByteSequence(self.data),))
                    return value
            uno.invoke(library,"insertByName",(spec["name"],uno.Any("com.sun.star.io.XInputStreamProvider",Provider(xml.encode("utf-8")))))
            item.update(status='candidate' if good else 'manual',records=records,original_xml=original.decode('utf-8'),candidate_xml=xml)
        except ValueError as error:item['reason']=str(error)
    return result


def helpers(specs):
    names=[s['name'] for s in specs if s['scope']=='dialog' and NAME.fullmatch(s['name'])]
    lines=['Option Explicit']
    for name in names:lines.append('Private mfDialog_'+name+' As Object')
    lines+=['Function MFUIDialog(name As String) As Object','    Select Case LCase(name)']
    for name in names:
        lines+=['    Case "'+name.lower()+'"','        If IsNull(mfDialog_'+name+') Or IsEmpty(mfDialog_'+name+') Then','            DialogLibraries.LoadLibrary("Standard")','            mfDialog_'+name+' = CreateUnoDialog(DialogLibraries.Standard.getByName("'+name+'"))','        End If','        MFUIDialog = mfDialog_'+name]
    lines+=['    Case Else','        Err.Raise 5, "Cellwright", "Unknown dialog"','    End Select','End Function',
'''Sub MFUIShow(name As String)
    MFUIDialog(name).execute()
End Sub
Sub MFUIHide(name As String)
    MFUIDialog(name).endExecute()
End Sub
Sub MFUIUnload(name As String)
    MFUIDialog(name).dispose()
    Select Case LCase(name)''']
    for name in names:lines+=['    Case "'+name.lower()+'"','        mfDialog_'+name+' = Nothing']
    lines+=['    End Select','End Sub', '''Function MFUIControl(scope As String, owner As String, name As String, kind As String) As Variant
    Dim model As Object, sheet As Object
    If scope = "dialog" Then
        model = MFUIDialog(owner).getControl(name).Model
    Else
        For Each sheet In ThisComponent.Sheets
            If LCase(sheet.CodeName) = LCase(owner) Then model = MFUIFind(sheet.DrawPage.Forms, name, 0)
        Next sheet
    End If
    MFUIControl = Array(model, kind)
End Function
Function MFUIFind(container As Object, name As String, depth As Integer) As Object
    Dim model As Object, i As Long, found As Object
    If depth > 32 Then Err.Raise 5, "Cellwright", "Control hierarchy too deep"
    For i = 0 To container.Count - 1
        model = container.getByIndex(i)
        If LCase(model.Name) = LCase(name) Then
            MFUIFind = model
            Exit Function
        End If
        If model.supportsService("com.sun.star.form.component.Form") Then
            found = MFUIFind(model, name, depth + 1)
            If Not IsNull(found) Then
                MFUIFind = found
                Exit Function
            End If
        End If
    Next i
End Function
Function MFUIProperty(kind As String, prop As String) As String
    Select Case prop
    Case "enabled": MFUIProperty = "Enabled"
    Case "visible": MFUIProperty = "EnableVisible"
    Case "caption": MFUIProperty = "Label"
    Case "text": MFUIProperty = "Text"
    Case "listindex": MFUIProperty = "SelectedItems"
    Case "value"
        If kind = "CheckBox" Or kind = "OptionButton" Then
            MFUIProperty = "State"
        Else
            MFUIProperty = "Text"
        End If
    Case Else: Err.Raise 5, "Cellwright", "Unsupported control property"
    End Select
End Function
Function MFUIGet(target As Variant, prop As String) As Variant
    Dim value
    value = target(0).getPropertyValue(MFUIProperty(target(1), prop))
    If prop = "value" And (target(1) = "CheckBox" Or target(1) = "OptionButton") Then
        If value = 2 Then Err.Raise 5, "Cellwright", "Tri-state needs manual migration"
        value = CBool(value)
    ElseIf prop = "listindex" Then
        If UBound(value) > 0 Then Err.Raise 5, "Cellwright", "Multi-selection needs manual migration"
        If UBound(value) < 0 Then
            value = -1
        Else
            value = value(0)
        End If
    End If
    MFUIGet = value
End Function
Sub MFUISet(target As Variant, prop As String, value As Variant)
    If prop = "value" And (target(1) = "CheckBox" Or target(1) = "OptionButton") Then
        value = Abs(CInt(CBool(value)))
    ElseIf prop = "listindex" Then
        If value <> Fix(value) Or value < -1 Or value > 32767 Then Err.Raise 5, "Cellwright", "Invalid list index"
        If value = -1 Then
            value = Array()
        Else
            value = Array(CInt(value))
        End If
    End If
    target(0).setPropertyValue(MFUIProperty(target(1), prop), value)
End Sub''']
    return '\n'.join(lines)+'\n'
