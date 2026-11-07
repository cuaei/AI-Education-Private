"""Student-written regression probe contract: a live application is provided."""
import os
import httpx

def main():
    base=os.environ.get('BASE_URL','http://127.0.0.1:8080')
    organizer=httpx.Client(base_url=base)
    alice=httpx.Client(base_url=base)
    bob=httpx.Client(base_url=base)
    for client,name in ((organizer,'organizer'),(alice,'student1'),(bob,'student2')):
        assert client.post('/api/auth/login',json={'username':name,'password':'Demo2026!'}).status_code==200
    event=organizer.post('/api/activities',json={'title':'学生回归案例','capacity':1,'deadline':'2099-10-08T00:00:00Z','starts_at':'2099-10-09T00:00:00Z'}).json()
    aid=event['id']
    first=alice.post(f'/api/activities/{aid}/register',json={})
    assert first.status_code==200
    second=alice.post(f'/api/activities/{aid}/register',json={})
    assert second.status_code==200 and second.json()['id']==first.json()['id'], '重复报名改变状态'
    assert alice.get(f'/api/activities/{aid}').json()['registered']==1, '重复请求重复占名额'
    assert bob.post(f'/api/activities/{aid}/register',json={}).status_code==409, '满额允许报名'
    assert bob.post(f"/api/registrations/{first.json()['id']}/cancel",json={}).status_code==403, '越权取消'
    assert alice.get(f'/api/activities/{aid}').json()['registered']==1

if __name__=='__main__':main()
