from fastapi.testclient import TestClient
from zipfile import ZipFile
from io import BytesIO
from backend.main import create_app

def test_example_starter_requires_student_and_is_downloadable(tmp_path):
    app=create_app(tmp_path,demo=True)
    with TestClient(app) as c:
        assert c.get('/api/java-route/example-starter').status_code==401
        c.post('/api/auth/login',json={'username':'teacher','password':'Teach2026!'})
        assert c.get('/api/java-route/example-starter').status_code==403
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        r=c.get('/api/java-route/example-starter')
        assert r.status_code==200
        with ZipFile(BytesIO(r.content)) as z:
            assert {'README.md','src/Main.java','src/CompetitionService.java'} <= set(z.namelist())
            assert '示例' in z.read('README.md').decode('utf-8')
