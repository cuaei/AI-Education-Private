"""Deterministic grading. Reference values never appear in failed-answer feedback."""
import io
import csv
import math
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from functools import lru_cache
import pandas as pd
from .course import FIELDS, START, dataset, METRIC_LABELS


def money(value):
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?',str(value)):
        raise ValueError('金额须为非负数，最多两位小数。')
    return int(Decimal(str(value))*100)


def change_rate(base,current):
    return round((current-base)/base*100,4) if base else None


def analyze_csv(content):
    if len(content)>2*1024*1024:
        raise ValueError('文件超过 2 MB，请缩小文件后重试。')
    try:
        text=content.decode('utf-8-sig')
        source=list(csv.reader(io.StringIO(text),strict=True))
        if not source or len(source[0])!=len(FIELDS):
            raise ValueError(f'CSV表头须有{len(FIELDS)}列。请使用课程模板。')
        for number,row in enumerate(source[1:],2):
            if len(row)!=len(FIELDS):raise ValueError(f'CSV第{number}行列数错误：预期{len(FIELDS)}列，实际{len(row)}列。请检查多余逗号、缺失字段或空白行；字段内逗号须用双引号包裹。尚未进入AI审阅。')
        frame=pd.read_csv(io.StringIO(text),dtype=str,keep_default_na=False)
    except (UnicodeError,csv.Error,pd.errors.ParserError,pd.errors.EmptyDataError) as e:
        raise ValueError('无法读取 CSV，请使用 UTF-8 编码及正确的逗号分隔格式。') from e
    if set(frame.columns)!=set(FIELDS):
        raise ValueError('CSV 字段必须为：'+', '.join(FIELDS))
    if len(frame)>10000:
        raise ValueError('文件超过 10,000 行。')
    duplicates=int(frame.duplicated().sum());frame=frame.drop_duplicates()
    conflicts=set(frame['order_id'][frame['order_id'].duplicated(keep=False)])
    rows=[];isolated=0;issues=[]
    for index,row in frame.iterrows():
        r=row.to_dict()
        try:
            if not all(r.values()) or r['order_id'] in conflicts:
                raise ValueError('必填值缺失或订单编号内容冲突')
            d=date.fromisoformat(r['order_date'])
            if not re.fullmatch(r'\d+',r['quantity']) or int(r['quantity'])<=0:
                raise ValueError('数量须为正整数')
            if r['category'] not in ('文具','服饰','纪念品','生活用品') or r['channel'] not in ('线上','线下'):
                raise ValueError('品类或渠道超出数据字典范围')
            price=money(r['unit_price']);refund=money(r['refund_amount']);gross=price*int(r['quantity'])
            if refund>gross:
                raise ValueError('退款额超过毛销售额')
            rows.append({**r,'gross_cents':gross,'refund_cents':refund,'net_cents':gross-refund,'day':(d-START).days})
        except (ValueError,TypeError) as error:
            isolated+=1
            if len(issues)<30: issues.append({'row':int(index)+2,'reason':str(error)[:200] or '检查必填值、日期、数值及订单冲突。'})
    gross=sum(r['gross_cents'] for r in rows);refund=sum(r['refund_cents'] for r in rows)
    return {'rows':rows,'duplicates':duplicates,'isolated':isolated,'issues':issues,'totals':{'gross':gross/100,'refund':refund/100,'net':(gross-refund)/100,'orders':len(rows),'aov':round((gross-refund)/100/len(rows),4) if rows else None,'refund_rate':round(refund/gross*100,4) if gross else None}}


@lru_cache(maxsize=2)
def reference(kind='A'):
    all_data=analyze_csv(dataset(kind));rows=all_data['rows']
    base=[r for r in rows if r['day']<28];current=[r for r in rows if r['day']>=28]
    b=sum(r['net_cents'] for r in base)/100;c=sum(r['net_cents'] for r in current)/100
    gross=sum(r['gross_cents'] for r in current);refund=sum(r['refund_cents'] for r in current)
    groups={}
    for dimension in ('category','channel'):
        groups[dimension]=[{'name':name,'baseline':sum(r['net_cents'] for r in base if r[dimension]==name)/100,'current':sum(r['net_cents'] for r in current if r[dimension]==name)/100} for name in sorted(set(r[dimension] for r in rows))]
    groups['weeks']=[{'name':f'第{i+1}周','baseline':None,'current':sum(r['net_cents'] for r in rows if r['day']//7==i)/100} for i in range(8)]
    return {'metrics':{'baseline_net':b,'current_net':c,'change_rate':change_rate(b,c),'aov':round(c/len(current),4),'refund_rate':round(refund/gross*100,4)},'groups':groups,'quality':{'duplicates':all_data['duplicates'],'isolated':all_data['isolated'],'orders':len(rows)},'rows':rows}


def close_number(actual,expected):
    if expected is None:return actual is None
    try:return math.isfinite(float(actual)) and abs(float(actual)-expected)<=0.01000001
    except (ValueError,TypeError):return False


def diagnose_metrics(values,expected,steps=None,source_version=''):
    steps=steps or {};items=[]
    for key,wanted in expected.items():
        if close_number(values.get(key),wanted):continue
        hypotheses=[];status='insufficient';skill='percentage_unit' if key in ('change_rate','refund_rate') else 'refund'
        method=steps.get(key,{})
        if not isinstance(method,dict):raise ValueError('计算步骤须为对象。')
        labels={'numerator','denominator','unit','formula'};numbers={'gross','refund','orders','quantity','baseline','current'}
        if set(method)-(labels|numbers):raise ValueError('计算方法字段不正确。')
        for field,value in method.items():
            if field in labels:
                if not isinstance(value,str) or len(value)>80:raise ValueError('计算方法字段不正确。')
            elif type(value)not in (int,float) or not math.isfinite(value) or abs(value)>1e12:raise ValueError('中间量须为有限数字。')
        if key=='refund_rate' and method.get('denominator')=='net':skill='refund'
        reported_error=(key=='aov' and method.get('denominator')=='quantity') or (key=='aov' and method.get('numerator')=='gross') or (key in ('current_net','baseline_net') and method.get('formula')=='gross') or (key=='refund_rate' and method.get('denominator')=='net') or (key=='change_rate' and method.get('denominator')=='current') or (key in ('change_rate','refund_rate') and method.get('unit')=='ratio')
        computed=None
        try:
            if key=='aov' and {'gross','refund','orders','quantity'}<=set(method):computed=(method['gross'] if method.get('numerator')=='gross' else method['gross']-method['refund'])/(method['quantity'] if method.get('denominator')=='quantity' else method['orders'])
            elif key in ('current_net','baseline_net') and {'gross','refund'}<=set(method):computed=method['gross'] if method.get('formula')=='gross' else method['gross']-method['refund']
            elif key=='refund_rate' and {'gross','refund'}<=set(method):computed=method['refund']/(method['gross']-method['refund'] if method.get('denominator')=='net' else method['gross'])*(1 if method.get('unit')=='ratio' else 100)
            elif key=='change_rate' and {'baseline','current'}<=set(method):computed=(method['current']-method['baseline'])/(method['current'] if method.get('denominator')=='current' else method['baseline'])*(1 if method.get('unit')=='ratio' else 100)
        except ZeroDivisionError:computed=None
        if reported_error:
            status='confirmed_step_error' if computed is not None and close_number(values.get(key),computed) else 'suspected'
            hypotheses.append('学生自报方法与课程口径有冲突。'+('中间量按该方法计算与提交结果一致，但不能证明这是唯一原因。' if status=='confirmed_step_error' else '还需要中间量与结果的一致性验证，不能直接确诊。'))
        elif key in ('change_rate','refund_rate') and wanted and (close_number(values.get(key),wanted/100) or close_number(values.get(key),wanted*100)):
            status='suspected';hypotheses.append('结果符合比率与百分数换算偏差的模式，须确认计算方法。')
        elif method:
            hypotheses.append('已提供的方法未发现明确口径冲突；请复核中间量、比较窗口及算术。')
        probe={'check_key':key,'question':'请说明本项采用的计算方法，系统只核对你的实际步骤。','fields':(['numerator','denominator'] if key=='aov' else ['formula'] if key in ('current_net','baseline_net') else ['numerator','denominator','unit'])}
        items.append({'check_key':key,'label':METRIC_LABELS[key],'status':status,'hypotheses':hypotheses,'skill_id':skill,'supporting_evidence_ids':[f'metric:{source_version}:{key}'],'reported_steps':method,'probe':probe})
    return items


def compare_metrics(values,expected,steps=None,source_version=''):
    checks=[{'key':k,'label':METRIC_LABELS[k],'submitted':values.get(k),'passed':close_number(values.get(k),v)} for k,v in expected.items()]
    diagnoses=diagnose_metrics(values,expected,steps,source_version)
    tags=[d['skill_id'] for d in diagnoses if d['status']=='confirmed_step_error']
    return {'score':sum(c['passed'] for c in checks)*5,'max_score':25,'passed':all(c['passed'] for c in checks),'checks':checks,'error_tags':list(dict.fromkeys(tags)),'diagnoses':diagnoses}


def evaluate_clean_csv(content,kind='A'):
    data=analyze_csv(content);ref=reference(kind)
    actual={r['order_id']:tuple(r[k] for k in FIELDS) for r in data['rows']}
    expected={r['order_id']:tuple(r[k] for k in FIELDS) for r in ref['rows']}
    checks=[{'key':'duplicates','label':'完全重复行已去除','passed':data['duplicates']==0},{'key':'isolated','label':'无效记录已隔离','passed':data['isolated']==0},{'key':'orders','label':'有效订单集合完整','passed':set(actual)==set(expected)},{'key':'values','label':'原始有效数据保持完整','passed':actual==expected}]
    return {'score':sum(c['passed'] for c in checks)*5,'max_score':20,'passed':all(c['passed'] for c in checks),'checks':checks,'error_tags':[] if all(c['passed'] for c in checks) else ['cleaning'],'quality':{k:data[k] for k in ('duplicates','isolated','issues')},'orders':len(data['rows'])}


def compare_groups(tables,kind='A'):
    expected=reference(kind)['groups'];checks=[]
    if not isinstance(tables,dict) or set(tables)!=set(expected):raise ValueError('只能提交品类、渠道和八周趋势。')
    for dim,rows in tables.items():
        if not isinstance(rows,list) or len(rows)>20:raise ValueError('分组表须为有限行数的列表。')
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'name','baseline','current'} or not isinstance(row['name'],str) or not 1<=len(row['name'])<=30:raise ValueError('分组行字段不正确。')
            for key in ('baseline','current'):
                value=row[key]
                if value is None and key=='baseline' and dim=='weeks':continue
                if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('金额须为有限数字。')
    for dim,wanted in expected.items():
        given=tables.get(dim,[])
        lookup={r.get('name'):r for r in given if isinstance(r,dict)}
        valid=len(given)==len(wanted) and len(lookup)==len(wanted) and all(r['name'] in lookup and close_number(lookup[r['name']].get('current'),r['current']) and (dim=='weeks' or close_number(lookup[r['name']].get('baseline'),r['baseline'])) for r in wanted)
        checks.append({'key':dim,'label':{'category':'品类比较','channel':'渠道比较','weeks':'八周趋势'}[dim],'passed':valid})
    return {'score':sum(c['passed'] for c in checks)*5,'max_score':15,'passed':all(c['passed'] for c in checks),'checks':checks,'error_tags':[] if all(c['passed'] for c in checks) else ['chart']}
