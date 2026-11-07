"""Versioned, original teaching material and reproducible synthetic transactions."""
import csv
import io
import random
from datetime import date, timedelta

VERSION = 'campus-retail-1.0'
FIELDS = ['order_id','order_date','category','channel','quantity','unit_price','refund_amount']
START = date(2026,1,5)
STAGES = ['起点诊断','数据检查','指标分析','图表证据','报告审阅','作品答辩','独立迁移','作品交付']
METRIC_LABELS = {'baseline_net':'前四周净销售额','current_net':'后四周净销售额','change_rate':'净销售额变化率（%）','aov':'后四周净客单价','refund_rate':'后四周金额退款率（%）'}
QUIZ_C = [
 {'question':'一笔订单金额 200 元，退款 50 元，净销售额是多少？','options':['200 元','150 元','250 元'],'answer':1,'skill':'refund'},
 {'question':'同一订单被完整复制两次，应如何处理？','options':['保留一条并记录去重','都保留','全部删除'],'answer':0,'skill':'cleaning'},
 {'question':'变化率模板要求百分数，下降 20% 应填写什么？','options':['-0.2','20','-20'],'answer':2,'skill':'percentage_unit'},
 {'question':'展示连续八周的销售变化，适合哪种图？','options':['饼图','折线图','无排序的文字列表'],'answer':1,'skill':'chart'},
 {'question':'看到线上销售下降，可以直接得出什么？','options':['宣传不足导致下降','消费者不再喜欢商品','线上净销售额在比较窗口内下降'],'answer':2,'skill':'evidence'},
 {'question':'没有进货和人工成本，能否计算利润？','options':['不能，需要成本数据','能，销售额就是利润','能，退款额就是成本'],'answer':0,'skill':'causality'},
]
QUIZ_D = [
 {'question':'销售 300 元，退款 60 元，净销售额是多少？','options':['300 元','360 元','240 元'],'answer':2,'skill':'refund'},
 {'question':'两行订单编号相同，但金额不同，应如何处理？','options':['随意留一条','隔离冲突并核查','把金额相加'],'answer':1,'skill':'cleaning'},
 {'question':'销售额从 80 变为 100，增长率的百分数是多少？','options':['25','20','0.25'],'answer':0,'skill':'percentage_unit'},
 {'question':'比较两个时间窗口的四个品类，哪种图适合？','options':['只显示店名','单值仪表','分组柱形图'],'answer':2,'skill':'chart'},
 {'question':'退款率上升，哪个结论表述最合理？','options':['退款占销售金额比重上升，原因需另查','产品质量一定变差','客服一定变差'],'answer':0,'skill':'evidence'},
 {'question':'做一项运营调整后，如何验证？','options':['凭感觉','预设指标与比较窗口，说明其他影响','只看点赞'],'answer':1,'skill':'causality'},
]
CARDS = {
 'refund': {'title':'把退款放回计算口径','body':'净销售额 = 数量 × 单价 − 退款金额。毛销售额与净销售额代表不同概念。先对一笔订单验证公式，再汇总。','question':'一笔订单购买 3 件，每件 20 元，退款 15 元。净销售额是多少？','answer':45,'unit':'元'},
 'cleaning': {'title':'清洗要保留可追溯记录','body':'完全重复行保留首次出现的一条；必填值缺失与同编号内容冲突的记录隔离，不自行补造金额。清洗后检查订单集合。','question':'有 12 行，其中 2 行为完全重复副本、1 行缺少数量。有效行数是多少？','answer':9,'unit':'行'},
 'percentage_unit': {'title':'区分比率和百分数','body':'变化率 =（当前值 − 基期值）÷ 基期值。模板填写百分数：0.25 应填写 25。基期为零时不可计算。','question':'净销售额从 100 元降到 80 元。填写变化率的百分数。','answer':-20,'unit':'%'},
 'chart': {'title':'让图表回答一个问题','body':'趋势用折线图；品类和渠道比较用分组柱形图。图表只引用已提交、已核验的数据，标明时间窗口和单位。','question':'前四周 100 元，后四周 80 元。柱形图中后期柱应标注多少元？','answer':80,'unit':'元'},
 'evidence': {'title':'把观察和假设分开','body':'先描述指标变化，再提出可能原因。交易表可以支持销售结构描述；营销效果和质量原因需要更多证据。','question':'两条建议中只有一条引用了真实指标，有证据的建议占比是多少百分数？','answer':50,'unit':'%'},
 'causality': {'title':'建议需要验证方法','body':'为建议写清行动、目标指标、观察周期及限制。没有成本不能判断利润；同一时期出现的变化不自动构成因果。','question':'毛销售额 100 元，退款 10 元。当前能确认的净销售额是多少？','answer':90,'unit':'元'},
}


def quiz_public(form='C'):
    return [{k:v for k,v in q.items() if k!='answer'} for q in (QUIZ_D if form=='D' else QUIZ_C)]


def quiz_grade(answers,form='C'):
    questions=QUIZ_D if form=='D' else QUIZ_C
    if len(answers)!=6 or any(type(a) is not int or a not in (0,1,2) for a in answers):
        raise ValueError('请完成六道题，每题选择一个选项。')
    correct=[a==q['answer'] for a,q in zip(answers,questions)]
    return {'score':sum(correct),'total':6,'correct':correct,'weak_skills':[q['skill'] for q,ok in zip(questions,correct) if not ok],'form':form}


def dataset(kind='A',dirty=True):
    if kind not in ('A','B'):
        raise ValueError('未知的实训数据。')
    rng=random.Random(20261012 if kind=='A' else 20261013)
    rows=[]
    cats=['文具','服饰','纪念品','生活用品']
    prices=[20,80,50,35]
    for i in range(512):
        day=(i*13)%56
        cat=rng.randrange(4)
        price=prices[cat]*100
        if day>=28 and ((kind=='A' and cat==0) or (kind=='B' and cat==1)):
            price=price*7//10
        quantity=rng.randint(1,3)
        gross=price*quantity
        refund=gross//2 if i%(11 if kind=='A' else 9)==0 else 0
        rows.append({'order_id':f'{kind}-{i+1:04}','order_date':str(START+timedelta(days=day)), 'category':cats[cat],'channel':'线上' if i%3 else '线下','quantity':str(quantity),'unit_price':f'{price/100:.2f}','refund_amount':f'{refund/100:.2f}'})
    if dirty:
        rows.extend(dict(r) for r in rows[:5])
        for i in range(3):
            row=dict(rows[20+i]); row['order_id']=f'{kind}-missing-{i}'; row['quantity']=''; rows.append(row)
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')
