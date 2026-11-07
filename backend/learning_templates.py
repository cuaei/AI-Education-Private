"""Bounded teaching variants. Only this server calculates their answer keys."""
import random
from . import course, engineering_course

VERSION='adaptive-2026.10.12.1'
PROJECTS=('retail','software-engineering')
KINDS={'retail':{'refund':['net','aov','refund_fraction','denominator'],'percentage_unit':['rate','refund_rate','zero'],'cleaning':['duplicates','conflict'],'chart':['value','display'],'evidence':['scope','observation'],'causality':['cause','validation']},'software-engineering':{'http':['status','resource'],'auth':['owner','role'],'state':['slots','repeat'],'transaction':['atomic','interleave'],'testing':['assertion','mutation'],'frontend':['conflict','loading']}}

def catalog(project):
    cards=course.CARDS if project=='retail' else engineering_course.CARDS
    return {f'{skill}.{kind}':{'skill_id':skill,'title':cards[skill]['title'],'kind':kind,'difficulty':[1,2,3]} for skill,kinds in KINDS[project].items() for kind in kinds}

def generate_exercise(project_id,template_id,difficulty,seed):
    if project_id not in PROJECTS or template_id not in catalog(project_id) or type(difficulty)is not int or difficulty not in (1,2,3):raise ValueError('题型或难度不允许。')
    rng=random.Random(seed);skill,kind=template_id.split('.');n=rng.randint(3,8);price=rng.randint(2,9)*10;refund=rng.randint(1,4)*5;gross=n*price;orders=rng.randint(2,5);capacity=rng.randint(4,12);name=f'学生{rng.randint(10,90)}'
    params={'quantity':n,'price':price,'refund':refund,'orders':orders,'capacity':capacity,'actor':name}
    question='';answer=None;unit='';choices=None
    def choice(stem,correct,wrong):
        nonlocal question,answer,choices
        question=stem;choices=[{'id':'correct','text':correct},*[{'id':f'distractor-{i}','text':text} for i,text in enumerate(wrong)]];rng.shuffle(choices);answer='correct'
    if project_id=='retail':
        if kind=='net':
            extra=rng.randint(1,4)*10 if difficulty>1 else 0;params['additional_gross']=extra
            question=f'一笔订单买{n}件，每件{price}元，退款{refund}元。'+(f'另有一笔未退款订单销售额{extra}元。' if extra else '')+'这些订单的净销售额合计是多少元？';answer=gross-refund+extra;unit='元'
        elif kind=='aov':question=f'{orders}笔有效订单共售出{n+orders}件商品，毛销售额{gross}元，退款{refund}元。后期净客单价是多少元？注意订单数与商品件数不同。';answer=round((gross-refund)/orders,4);unit='元/单'
        elif kind=='refund_fraction':question=f'本期毛销售额{gross}元，退款金额{refund}元，净额{gross-refund}元。按“退款金额÷毛销售额×100”计算金额退款率，百分数应填多少？';answer=round(refund/gross*100,4);unit='%'
        elif kind=='denominator':choice(f'毛销售额{gross}元，退款{refund}元，净额{gross-refund}元。计算金额退款率时，分母应是什么？','毛销售额',['净销售额','有效订单数'])
        elif kind=='rate':
            base=rng.randint(3,12)*100;delta=rng.choice([-30,-20,-10,10,20,25,40]);current=base*(100+delta)//100;params.update(base=base,current=current)
            question=f'前四周净销售额{base}元，后四周{current}元。变化率以百分数填写（例如增长10%填10），应填多少？';answer=round((current-base)/base*100,4);unit='%'
        elif kind=='zero':choice(f'前期没有订单，净销售额为0；本期净销售额{gross}元。增长率应如何报告？','基期为零，增长率不可计算；单独报告金额变化',['增长率为0%','增长率为100%'])
        elif kind=='refund_rate':question=f'本期毛销售额{gross}元，退款{refund}元。金额退款率要填写百分数，不填写小数比率。应填多少？';answer=round(refund/gross*100,4);unit='%'
        elif kind=='duplicates':
            total=n+orders+4;copies=rng.randint(1,3);missing=1 if difficulty==1 else 2;params.update(total=total,copies=copies,missing=missing)
            question=f'CSV有{total}行。其中{copies}行是完全重复的额外副本，另有{missing}行缺少必填数量，这两类不重叠。去重、隔离后有效行数是多少？';answer=total-copies-missing;unit='行'
        elif kind=='conflict':choice(f'两行订单编号都是R-{n}，一行金额{price}元，另一行{price+refund}元。其余字段相同。应怎样处理？','隔离冲突并核查原始记录，不能随意选金额',['随机留一行，当作重复','两行金额相加后合并'])
        elif kind=='value':question=f'已核验同一品类前期净额{gross}元、后期净额{gross-refund}元。分组柱形图后期柱应取多少元？';answer=gross-refund;unit='元'
        elif kind=='display':choice(f'要比较{n}个连续周的净销售额，横轴保留周序、纵轴标元。哪个展示最能回答趋势问题？','按周顺序的折线图',['把周序打乱的柱状图','各周金额相加后的一个仪表值'])
        elif kind=='scope':choice(f'只有订单、数量、价格、退款、日期与渠道，线上净额从{gross}降至{gross-refund}元。哪个结论有现有数据支持？','比较窗口内线上净销售额下降',['广告投放一定失败','商品质量一定变差'])
        elif kind=='observation':choice(f'金额退款率从{n}%升至{n+orders}%。没有退款原因字段。哪个表达区分了观察与假设？','退款比重上升；质量原因仍需调查',['退款比重上升证明商品质量下降','退款比重上升证明客服态度不好'])
        elif kind=='cause':choice(f'店铺发帖后一周净销售额增加{n}%，同时恰逢开学。能直接确认什么？','销售额与发帖同期增加，但无法仅凭同期变化证明因果',['销售增加全部由发帖造成','发帖没有作用，因为开学也发生了'])
        elif kind=='validation':choice(f'你建议调整线上推广，计划观察{n}周。怎样检验建议是否有效？','预设指标和比较窗口，设置适当对照并记录其他变化',['只询问店长感觉是否更好','只统计帖子点赞而不看订单'])
    else:
        if kind=='status':choice(f'{name}没有登录，服务端首先做身份验证，收到报名请求。应返回哪个状态？','401：要求登录',['403：已有身份但权限不足','200：相信请求里的用户名'])
        elif kind=='resource':choice(f'{name}已登录且有访问权限，查询活动ID {capacity}，资源确实不存在。应返回？','404：资源不存在',['401：未登录','200：自动编造活动'])
        elif kind=='owner':choice(f'报名归{ name }所有，另一个已登录学生修改报名ID来取消它。服务端应怎样做？','校验归属并拒绝操作，保留原报名和名额',['信任前端隐藏按钮，无需后端检查','允许取消，只在页面提示不是自己的'])
        elif kind=='role':choice(f'学生角色请求查看活动{capacity}的组织者报名名单，身份已认证。应如何处理？','403：角色无权访问，不能返回名单',['200：登录就可查看任何名单','仅隐藏网页按钮但仍返回名单'])
        elif kind=='slots':
            occupied=rng.randint(2,capacity);params['occupied']=occupied
            question=f'容量{capacity}，当前有效报名{occupied}人。一名有效报名者取消后，同一取消请求再次提交，其他记录不变。最终剩余名额是多少？';answer=capacity-occupied+1;unit='个'
        elif kind=='repeat':choice(f'{name}已经有效报名容量{capacity}的活动，又提交一次相同报名请求。正确结果是什么？','返回本人当前报名状态，有效人数不再增加',['新建第二条有效报名并再占一个名额','删除第一次报名来避免重复'])
        elif kind=='atomic':choice(f'活动剩最后一个名额，{n}个请求同时到达。哪种实现能保证不会超额？','容量检查和报名写入在受控原子事务中完成',['只在浏览器禁用按钮','查询容量后结束事务，再分别插入'])
        elif kind=='interleave':choice('容量为1且人数为0。A读取0，B读取0，A插入报名，B也插入报名；检查和写入不是原子操作。直接问题是什么？','两个请求都依据旧人数放行，可能超过容量',['页面字体发生变化','重复请求自动变成了同一个用户'])
        elif kind=='assertion':choice(f'要发现{ name }重复取消导致多释放名额的缺陷，哪个断言最有效？','连续取消两次后，剩余名额只比初始多1个',['每次请求都没有异常就足够','测试文件行数超过100'])
        elif kind=='mutation':choice(f'你的测试对正确报名实现通过，对一个故意移除归属检查的变体也通过。应怎样解释？','这组测试还不能发现该权限故障，应增加越权断言',['两个版本都通过，说明测试非常有效','删除权限测试即可提高通过率'])
        elif kind=='conflict':choice(f'页面显示活动{capacity}有名额，但报名API实际返回409满额。页面应怎样处理？','展示满额原因，并以服务端结果更新状态',['仍显示成功，因为旧页面显示有名额','无限重复发送请求直到成功'])
        elif kind=='loading':choice(f'{name}点击报名，请求仍在处理中，用户又点击。合适的处理是什么？','显示加载并避免重复操作，后端仍保证幂等',['不显示状态，发送更多请求','只靠按钮禁用就省去后端幂等'])
    if answer is None:raise ValueError('题型未实现。')
    cards=course.CARDS if project_id=='retail' else engineering_course.CARDS
    topic=cards[skill]['title']
    hints=[f'先回想「{topic}」的规则，再找题目要求的量或行为。',cards[skill]['body'],('同类例子：销售2件、每件10元，退款5元。先求毛额，再扣退款；计算客单价还须使用订单数。' if skill=='refund' else '同类例子：从50变为60时，先求差额，再除基期，最后按输出单位处理。' if skill=='percentage_unit' else '另一个场景中，重复提交同一操作不应重复改变状态。写出操作前后状态，再逐步应用规则。' if project_id!='retail' else f'把「{topic}」拆成输入、规则、可确认的结果。原因解释需要额外证据，不应由数字变化直接推断。')]
    # IDs encode position, never which choice is correct.
    if choices:
        for i,o in enumerate(choices):
            if o['id']==answer:answer='choice-'+str(i)
            o['id']='choice-'+str(i)
    return {'template_id':template_id,'template_version':VERSION,'seed':seed,'parameters':params,'skill_id':skill,'difficulty':difficulty,'question':question,'options':choices or [],'answer_type':'choice' if choices else 'number','unit':unit,'expected_answer':answer,'validator_version':VERSION,'hints':hints}
