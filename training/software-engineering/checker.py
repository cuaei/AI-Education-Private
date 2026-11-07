"""Trusted checker, run in a separate container from student code."""
import concurrent.futures
import json
import os
import time
import traceback
import httpx
from playwright.sync_api import sync_playwright

BASE='http://127.0.0.1:8080'
checks=[]

class InfrastructureError(RuntimeError):pass

def browser_start(playwright):
    try:return playwright.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    except Exception as e:raise InfrastructureError('浏览器运行环境不可用，尚未计分。') from e

def client(name=None):
    c=httpx.Client(base_url=BASE,timeout=12)
    if name:
        r=c.post('/api/auth/login',json={'username':name,'password':'Demo2026!'})
        assert r.status_code==200,f'登录应200，实际{r.status_code}'
    return c

def event(capacity=2,deadline='2099-10-08T12:00:00Z',starts='2099-10-09T12:00:00Z'):
    r=client('organizer').post('/api/activities',json={'title':'验收活动 '+str(time.time_ns()),'capacity':capacity,'deadline':deadline,'starts_at':starts})
    assert r.status_code==200,f'发布应200，实际{r.status_code}'
    return r.json()['id']

def register(c,aid,waiting=False):return c.post(f'/api/activities/{aid}/register',json={'waitlist':waiting})
def detail(aid):return client().get(f'/api/activities/{aid}').json()
def must(condition,message):
    if not condition:raise AssertionError(message)

def check(key,label,weight,dimension,fn):
    try:fn();passed=True;actual='实际运行符合公开验收规则。'
    except InfrastructureError:raise
    except Exception as e:passed=False;actual=str(e)[:700] or type(e).__name__
    checks.append({'key':key,'label':label,'weight':weight,'dimension':dimension,'passed':passed,'expected':label,'actual':actual,'source':'runtime'})

def authentication():
    aid=event();r=register(client(),aid)
    must(r.status_code==401,f'未登录报名应401，实际{r.status_code}')
    r=client('student1').post('/api/activities',json={'title':'不能发布','capacity':1,'deadline':'2099-10-08T12:00:00Z','starts_at':'2099-10-09T12:00:00Z'})
    must(r.status_code==403,f'学生发布应403，实际{r.status_code}')

def publishing():
    aid=event(3);d=detail(aid)
    must(d['capacity']==3 and d['registered']==0 and d['remaining']==3,'新活动容量或人数错误')
    must(any(e['id']==aid for e in client().get('/api/activities').json()),'列表没有新活动')

def duplicate():
    aid=event(2);c=client('student1');a=register(c,aid);b=register(c,aid)
    must(a.status_code==200 and b.status_code==200,'有效重复报名应幂等200')
    must(a.json()['id']==b.json()['id'] and detail(aid)['registered']==1,'重复请求生成第二条有效报名或重复占名额')

def cancelling():
    aid=event(2);c=client('student1');r=register(c,aid).json();url=f"/api/registrations/{r['id']}/cancel"
    must(c.post(url,json={}).status_code==200 and c.post(url,json={}).status_code==200,'取消及重复取消应幂等200')
    must(detail(aid)['registered']==0 and detail(aid)['remaining']==2,'重复取消改变人数')
    again=register(c,aid);must(again.status_code==200,'截止前不能重新报名')
    rows=c.get('/api/registrations/mine').json()
    must(any(x['id']==r['id'] and x['status']=='cancelled' for x in rows),'取消历史未保留')
    must(any(x['activity_id']==aid and x['status']=='confirmed' for x in rows),'我的报名缺少有效记录')

def ownership():
    aid=event();alice=client('student1');bob=client('student2');r=register(alice,aid).json()
    must(bob.post(f"/api/registrations/{r['id']}/cancel",json={}).status_code==403,'他人取消未拒绝403')
    must(detail(aid)['registered']==1,'越权请求改变了人数')
    must(all(row['student_id']==2 for row in bob.get('/api/registrations/mine').json()),'我的报名泄露他人记录')

def roster():
    aid=event();register(client('student1'),aid)
    url=f'/api/activities/{aid}/roster'
    must(client('student1').get(url).status_code==403,'学生可读取组织者名单')
    must(client('organizer2').get(url).status_code==403,'其他组织者可读取名单')
    r=client('organizer').get(url);must(r.status_code==200 and len(r.json())==1,'活动所有者名单错误')

def invalid_input():
    c=client('organizer')
    for capacity in (0,-1,'2'):
        r=c.post('/api/activities',json={'title':'非法','capacity':capacity,'deadline':'2099-10-08T12:00:00Z','starts_at':'2099-10-09T12:00:00Z'})
        must(r.status_code==422,f'非法容量{capacity}应422，实际{r.status_code}')
    r=c.post('/api/activities',json={'title':'时间错误','capacity':1,'deadline':'2099-10-10T00:00:00Z','starts_at':'2099-10-09T00:00:00Z'})
    must(r.status_code==422,'截止晚于开始未拒绝')

def deadline():
    aid=event(deadline='2099-10-01T00:00:00Z');r=register(client('student1'),aid)
    must(r.status_code==409,'截止瞬间仍允许报名')
    must(detail(aid)['closed'] is True,'页面截止标记错误')

def nonexistent():
    c=client('student1')
    must(register(c,9999999).status_code==404,'不存在活动报名应404')
    must(c.post('/api/registrations/9999999/cancel',json={}).status_code==404,'不存在报名取消应404')

def concurrency():
    aid=event(1);a=client('student3');b=client('student4')
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda c:register(c,aid),[a,b]))
    statuses=sorted(r.status_code for r in results)
    must(statuses==[200,409],f'最后名额应1人成功1人冲突，实际{statuses}')
    must(detail(aid)['registered']==1,'并发后人数错误')

def capacity():
    aid=event(1);register(client('student1'),aid);r=register(client('student2'),aid)
    must(r.status_code==409,f'满额应409，实际{r.status_code}')
    must(detail(aid)['remaining']==0,'剩余名额为负或不一致')

def ui_basic():
    with sync_playwright() as p:
        browser=browser_start(p)
        page=browser.new_page();page.goto(BASE,wait_until='networkidle')
        page.get_by_role('heading',name='校园活动报名',exact=True).wait_for()
        page.get_by_label('用户名',exact=True).fill('student1');page.get_by_label('密码',exact=True).fill('Demo2026!')
        page.get_by_role('button',name='登录',exact=True).click()
        page.get_by_role('heading',name='student1 · student',exact=True).wait_for()
        page.get_by_role('heading',name='我的报名',exact=True).wait_for()
        # The learner must provide the actual organizer UI, not only APIs.
        page.get_by_label('用户名',exact=True).fill('organizer');page.get_by_role('button',name='登录',exact=True).click()
        page.get_by_role('heading',name='发布活动',exact=True).wait_for()
        title='页面发布 '+str(time.time_ns())
        page.get_by_label('活动名称',exact=True).fill(title)
        page.get_by_role('button',name='发布',exact=True).click()
        card=page.locator('article').filter(has=page.get_by_role('heading',name=title,exact=True))
        card.get_by_role('button',name='查看名单',exact=True).click()
        page.get_by_role('heading',name='报名名单',exact=True).wait_for()
        browser.close()

def ui_state(waiting=False):
    aid=event(1);alice=client('student1');register(alice,aid)
    if waiting:name='student2';expected='waiting'
    else:
        # Cancel API seed so the browser itself must perform registration.
        seed=alice.get('/api/registrations/mine').json()
        registration=next(r for r in seed if r['activity_id']==aid and r['status']=='confirmed')
        alice.post(f"/api/registrations/{registration['id']}/cancel",json={})
        name='student1';expected='confirmed'
    title=detail(aid)['title']
    with sync_playwright() as p:
        browser=browser_start(p)
        page=browser.new_page();page.goto(BASE,wait_until='networkidle')
        page.get_by_label('用户名',exact=True).fill(name);page.get_by_label('密码',exact=True).fill('Demo2026!');page.get_by_role('button',name='登录',exact=True).click()
        page.get_by_role('heading',name=name+' · student',exact=True).wait_for()
        card=page.locator('article').filter(has=page.get_by_role('heading',name=title,exact=True))
        card.get_by_role('button',name='加入候补' if waiting else '报名',exact=True).click()
        panel=page.locator('section').filter(has=page.get_by_role('heading',name='我的报名',exact=True))
        item=panel.locator('article').filter(has_text=title).filter(has=page.get_by_text(f'({expected})',exact=False));item.get_by_text(f'({expected})',exact=False).wait_for()
        if not waiting:
            page.get_by_label('用户名',exact=True).fill('student2');page.get_by_role('button',name='登录',exact=True).click()
            page.get_by_role('heading',name='student2 · student',exact=True).wait_for()
            card.get_by_role('button',name='报名',exact=True).click();page.get_by_role('alert').filter(has_text='满').wait_for()
            page.get_by_label('用户名',exact=True).fill('student1');page.get_by_role('button',name='登录',exact=True).click()
            page.get_by_role('heading',name='student1 · student',exact=True).wait_for()
            item.get_by_role('button',name='取消报名',exact=True).click()
            panel.locator('article').filter(has_text=title).get_by_text('(cancelled)',exact=False).last.wait_for()
        browser.close()

def waitlist_state():
    aid=event(1);a=client('student1');b=client('student2');register(a,aid)
    r=register(b,aid,True);must(r.status_code==200 and r.json()['status']=='waiting','满额时无法进入候补')
    must(detail(aid)['registered']==1,'候补占用有效名额')
    must(register(b,aid,True).json()['id']==r.json()['id'],'重复候补再次入队')

def waitlist_fifo():
    aid=event(1);a=client('student1');b=client('student2');c=client('student3')
    first=register(a,aid).json();second=register(b,aid,True).json();third=register(c,aid,True).json()
    a.post(f"/api/registrations/{first['id']}/cancel",json={})
    rows=client('organizer').get(f'/api/activities/{aid}/roster').json();states={r['id']:r['status'] for r in rows}
    must(states[second['id']]=='confirmed' and states[third['id']]=='waiting','没有按稳定先后递补最早候补')
    must(detail(aid)['registered']==1,'递补人数不一致')
    c.post(f"/api/registrations/{third['id']}/cancel",json={});must(detail(aid)['registered']==1,'取消候补释放了有效名额')

def waitlist_boundary():
    aid=event(1);a=client('student1');b=client('student2');c=client('student3')
    first=register(a,aid).json();second=register(b,aid,True).json();register(c,aid,True)
    must(c.post(f"/api/registrations/{second['id']}/cancel",json={}).status_code==403,'他人候补可越权取消')
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _:a.post(f"/api/registrations/{first['id']}/cancel",json={}),range(2)))
    rows=client('organizer').get(f'/api/activities/{aid}/roster').json()
    must(sum(r['status']=='confirmed' for r in rows)==1,'重复并发取消递补多个人')
    expired=event(1,'2099-10-01T00:00:00Z');must(register(b,expired,True).status_code==409,'截止后仍可候补')

def main():
    for _ in range(90):
        try:
            if httpx.get(BASE+'/api/activities',timeout=1).status_code==200:break
        except Exception:pass
        time.sleep(.5)
    else:raise RuntimeError('提交的应用未成功启动，请查看构建/启动日志。')
    # Infrastructure failures must not become student deductions or consume B attempts.
    with sync_playwright() as p:
        browser=browser_start(p);browser.close()
    if os.environ.get('CHECK_KIND','A')=='B':
        check('B-STATE','候补状态、重复请求与有效人数',5,'transfer',waitlist_state)
        check('B-FIFO','稳定先后、递补与候补取消',5,'transfer',waitlist_fifo)
        check('B-BOUNDARY','并发、截止及资源归属',5,'transfer',waitlist_boundary)
        check('B-UI','页面真实显示候补状态',5,'transfer',lambda:ui_state(True))
    else:
        for key,label,fn in [('AUTH','认证和学生角色限制',authentication),('PUBLISH','组织者发布、列表和详情',publishing),('DUPLICATE','重复报名保持幂等',duplicate),('CANCEL','取消幂等、重报及本人历史',cancelling),('OWNERSHIP','取消归属与本人记录',ownership),('ROSTER','组织者名单权限',roster)]:check('A-'+key,label,5,'business',fn)
        check('A-UI-LOGIN','实际页面登录、活动及本人报名入口',5,'frontend',ui_basic)
        check('A-UI-STATE','实际报名状态与取消交互',5,'frontend',ui_state)
        for key,label,fn in [('INPUT','非法容量和截止输入拒绝',invalid_input),('DEADLINE','截止瞬间停止报名',deadline),('MISSING','不存在资源返回404',nonexistent),('CONCURRENCY','同时抢最后名额只成功一人',concurrency),('CAPACITY','满额拒绝且剩余不为负',capacity)]:check('A-'+key,label,2,'boundary',fn)
    print(json.dumps({'checks':checks},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'environment_error':str(e)[:500]},ensure_ascii=False));raise SystemExit(2)
