# SPDX-License-Identifier: EUPL-1.2
"""Actionable candidate checklists and an allowlisted review summary."""
import collections
import re


def next_action(reason):
    value=reason.lower()
    if any(word in value for word in ('control','form','event','button','dialog')):return 'Use the form/control recipe, review the layout and reconnect only the intended event.'
    if any(word in value for word in ('range','sort','filter','worksheet','sheet','copy')):return 'Use the range recipe with explicit sheets, ranges and arguments; compare representative cells.'
    if any(word in value for word in ('query','connection','provider','pandas')):return 'Review the data-source recipe and compare a saved output table before enabling refresh.'
    if any(word in value for word in ('com','windows','shell','declare','outlook')):return 'Replace this external dependency using the manual recipe; review permissions and side effects.'
    return 'Open the original and diff at this location, make the described edit and add a focused comparison case.'


def checklist(report):
    items=[]
    def add(status,location,reason,action,rule=None,line=None):
        items.append({'status':status,'location':location,'line':line,'rule_id':rule,'reason':reason,'next_action':action})
    for module in report.get('modules',[]):
        add('candidate_generated',module['name'],str(len(module.get('rewrites',[])))+' deterministic rewrite(s); source and diff retained','Review the source diff. A generated candidate has not been tested.')
        for todo in module['todos']:add('manual_work_required',module['name'],todo['reason'],next_action(todo['reason']),todo.get('rule_id'),todo.get('line'))
    for query in report.get('power_queries',[]):
        for todo in query.get('todos',[]):add('manual_work_required',query['name'],todo['reason'],next_action('query'),todo.get('rule_id'),todo.get('line'))
    for control in report.get('buttons',{}).get('records',[]):
        location=' / '.join(v for v in [control.get('sheet'),control.get('control')] if v) or control.get('before','Workbook button')
        rewritten=control['status']=='rewritten'
        add('candidate_generated' if rewritten else 'manual_work_required',location,'Event binding generated' if rewritten else control['reason'],'Inspect the saved control and compare the intended interaction.' if rewritten else next_action('control'))
    for interface in report.get('user_interfaces',[]):
        add('candidate_generated' if interface['status']=='candidate' else 'manual_work_required',interface['name'],interface.get('reason','Imported layout retained as an editable dialog candidate'),'Inspect positions, captions, tab order and every control before use.')
        for record in interface.get('records',[]):
            add('candidate_generated' if record['status']=='rewritten' else 'manual_work_required',interface['name']+' / '+record.get('control',record.get('procedure','layout')),record.get('reason','Event binding generated'),next_action('control'))
    for finding in report.get('workbook_findings',[]):
        status='unknown_coverage' if finding['verdict']=='unknown' else 'manual_work_required'
        add(status,'Workbook',finding['messages'][0],'Inspect skipped or unreadable parts separately; candidate generation does not resolve unknown coverage.' if status=='unknown_coverage' else next_action(finding['messages'][0]),finding['rule_id'],finding.get('line'))
    return {'conversion_status':'manual_work_required' if any(i['status']=='manual_work_required' for i in items) else 'candidate_generated', 'test_status':'not_tested', 'coverage_status':'unknown' if any(i['status']=='unknown_coverage' for i in items) else 'inspected_scope', 'items':items}


def handoff(report, evidence=(), include_identifiers=False):
    """Never export code, paths, hashes, free-text reasons or captured cell contents."""
    rules=collections.Counter()
    for item in report['checklist']['items']:
        rule=item.get('rule_id')
        if isinstance(rule,str) and re.fullmatch(r'[A-Z][A-Z0-9-]{1,60}',rule):rules[rule]+=1
    result={'schema_version':'1','purpose':'Optional migration review','target':report['target'],'coverage_status':report['checklist']['coverage_status'], 'conversion_status':report['checklist']['conversion_status'], 'test_status':'selected_tests_passed' if evidence and all(case.get('passed') is True for case in evidence) else 'selected_tests_differ' if evidence else 'not_tested', 'tests':{'cases':len(evidence),'passed':sum(case.get('passed') is True for case in evidence)}, 'modules':[], 'interfaces':len(report.get('user_interfaces',[])), 'rule_counts':dict(rules), 'removed':['workbook and artifact paths','source code and diffs','captured values and formulas','hashes','owner details and free-text notes','module and routine names' if not include_identifiers else 'control and query names']}
    for index,module in enumerate(report['modules']):
        item={'label':module['name'] if include_identifiers else 'Module '+str(index+1),'kind':module['kind'],'rewrites':len(module.get('rewrites',[])),'unresolved':len(module['todos'])}
        if include_identifiers:item['routines']=[p['name'] for p in module.get('procedures',[]) if isinstance(p,dict)]
        result['modules'].append(item)
    return result
