"""Account-owned introductory tutorials, independent of grades and AI usage."""
import time
from fastapi import Depends,HTTPException

VERSION='spotlight-2026.10.12.1'
SCOPES={'library':3,'retail':6,'software-engineering':6}

def mount_tutorial(app,store,student):
    def check_scope(scope):
        if scope not in SCOPES:raise HTTPException(404,'这个页面没有实训教程。')
    def response(uid,scope):
        record=store.load_tutorial(uid,scope,VERSION)
        return {'scope':scope,'version':VERSION,'step_count':SCOPES[scope],'status':record['status'],'step':record['step']}

    @app.get('/api/tutorial/{scope}')
    def get_tutorial(scope:str,current=Depends(student)):
        check_scope(scope)
        with store.user_lock(current['id']):return response(current['id'],scope)

    @app.post('/api/tutorial/{scope}')
    def update_tutorial(scope:str,payload:dict,current=Depends(student)):
        check_scope(scope)
        if payload.get('version')!=VERSION:raise HTTPException(409,'教程版本已更新，请重新打开教程。')
        status=payload.get('status');step=payload.get('step')
        if not isinstance(status,str) or status not in ('in_progress','completed','skipped'):raise HTTPException(422,'教程状态无效，请重新打开教程。')
        if type(step)is not int or not 0<=step<SCOPES[scope]:raise HTTPException(422,'教程步骤超出当前页面范围。')
        if status=='completed' and step!=SCOPES[scope]-1:raise HTTPException(422,'请在教程最后一步确认完成，或使用跳过。')
        with store.user_lock(current['id']):
            existing=store.load_tutorial(current['id'],scope,VERSION)
            # Late requests from a previous tab cannot reopen a dismissed tour.
            if existing['status'] in ('completed','skipped') and status=='in_progress':return response(current['id'],scope)
            if existing['status']=='completed' and status=='skipped':return response(current['id'],scope)
            store.save_tutorial(current['id'],scope,VERSION,{'status':status,'step':step,'updated':time.time()})
            return response(current['id'],scope)
