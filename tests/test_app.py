import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db import connect, password_hash
from app.main import create_app
from app.rules import normalize

PASSWORD = "only-for-test-12345"
VALID = {"q1": {"a": "k"}, "q2": "a", "q3": "a", "q4": ["n"]}


@pytest.fixture(scope="session")
def hashed():
    return password_hash(PASSWORD)


@pytest.fixture
def env(tmp_path, hashed):
    root = tmp_path / "images"
    batch = root / "batch"
    batch.mkdir(parents=True)
    for i in range(12):
        Image.new("L", (16,16), 30+i).save(batch / f"image-{i}.png")
    db_path = tmp_path / "app.sqlite3"
    app = create_app(db_path, root, False)
    with connect(db_path) as db:
        for name, role in [("admin", "admin"), ("alice", "annotator"), ("bob", "annotator")]:
            db.execute("INSERT INTO users(username,display_name,password_hash,role) VALUES(?,?,?,?)", (name,name,hashed,role))
    clients = {}
    for name in ["admin", "alice", "bob"]:
        client = TestClient(app)
        assert client.post("/api/login",json={"username":name,"password":PASSWORD}).status_code == 200
        client.headers["X-CSRF-Token"] = client.get("/api/me").json()["csrf"]
        clients[name] = client
    yield {"app": app, "clients": clients, "db": db_path, "root": root, "batch": batch}
    for client in clients.values():
        client.close()


def activate(env, mode="independent"):
    client = env["clients"]["admin"]
    result = client.post("/api/admin/datasets",json={"name":"测试集", "path":"batch", "mode":mode})
    assert result.status_code == 200, result.text
    did = result.json()["id"]
    assert client.post(f"/api/admin/datasets/{did}/activate").status_code == 200
    return did


def next_task(client):
    result = client.post("/api/tasks/next")
    assert result.status_code == 200, result.text
    return result.json()["task"]


def submit(client, task, labels=VALID):
    return client.post(f"/api/tasks/{task['id']}/submit",json={"labels":labels,"revision":task["revision"]})


@pytest.mark.parametrize("q1", [{"b":"i"},{"a":"k","c":"i"},{"d":"k"},{"a":"j","b":"j"}])
def test_mixed_layer_rule(q1):
    result=normalize({**VALID,"q1":q1},True)
    assert result["q2"] == result["q3"] == "n"


@pytest.mark.parametrize("labels", [
    {**VALID,"q1":{}}, {**VALID,"q1":{"a":None}}, {**VALID,"q1":{"a":"z"}},
    {**VALID,"q2":"n"}, {**VALID,"q3":None}, {**VALID,"q4":[]},
    {**VALID,"q4":["a","n"]}, {**VALID,"q4":["a","a"]}, {**VALID,"q4":["f"]},
])
def test_invalid_final_labels(labels):
    with pytest.raises(ValueError):
        normalize(labels,True)


def test_incomplete_drafts_permitted():
    assert normalize({"q1":{"a":None},"q2":None,"q3":None,"q4":[]})["q1"] == {"a":None}


def test_auth_and_csrf(env):
    anonymous=TestClient(env["app"])
    assert anonymous.get("/api/history").status_code == 401
    assert anonymous.get("/api/admin/export?dataset_id=1").status_code == 401
    assert anonymous.get("/api/manual").status_code == 401
    assert env["clients"]["alice"].get("/api/admin/overview").status_code == 403
    client=env["clients"]["alice"]
    assert client.post("/api/tasks/next",headers={"X-CSRF-Token":"bad"}).status_code == 403
    assert client.post("/api/tasks/next",headers={"Origin":"https://evil.example"}).status_code == 403
    assert anonymous.post("/api/login",json={"username":"alice","password":"wrong"}).status_code == 401


def test_independent_random_queues_resume_and_complete(env):
    activate(env)
    alice,bob = env["clients"]["alice"],env["clients"]["bob"]
    first=next_task(alice)
    assert next_task(alice)["id"] == first["id"]
    next_task(bob)
    with connect(env["db"]) as db:
        order_a=[r[0] for r in db.execute("SELECT image_id FROM assignments WHERE user_id=2 ORDER BY position")]
        order_b=[r[0] for r in db.execute("SELECT image_id FROM assignments WHERE user_id=3 ORDER BY position")]
    assert sorted(order_a)==sorted(order_b) and len(set(order_a))==12
    assert order_a!=order_b
    for index in range(12):
        task=next_task(alice)
        assert task["image_id"]==order_a[index]
        assert submit(alice,task).status_code==200
    assert next_task(alice) is None
    assert alice.get('/api/progress').json()['completed']==12
    assert bob.get('/api/progress').json()['completed']==0


def test_draft_restoration_revision_conflict_and_audit(env):
    did=activate(env)
    client=env["clients"]["alice"]
    task=next_task(client)
    partial={"q1":{"a":None},"q4":[]}
    result=client.put(f"/api/tasks/{task['id']}/draft",json={"labels":partial,"revision":0})
    assert result.status_code==200
    restored=next_task(client)
    assert restored["has_draft"] and restored["labels"]["q1"]=={"a":None}
    assert submit(client,task).status_code==409
    assert submit(client,restored).status_code==200
    saved=client.get(f"/api/tasks/{task['id']}").json()
    assert saved["submitted"] and not saved["has_draft"]
    assert submit(client,saved,{**VALID,"q2":"b"}).status_code==200
    with connect(env["db"]) as db:
        assert db.execute("SELECT count(*) FROM annotation_audit").fetchone()[0]==2
    export=env["clients"]["admin"].get(f"/api/admin/export?dataset_id={did}&format=jsonl")
    record=json.loads(export.text)
    assert record["q2"]=="b" and record["q1_a"]=="k" and record["manual_version"]=="20261027"
    assert len(record["sha256"])==64
    assert len(client.get('/api/history').json())==1


def test_private_images_and_unchanged_pixels(env):
    activate(env)
    client=env["clients"]["alice"]
    task=next_task(client)
    with connect(env["db"]) as db:
        path=env["batch"] / db.execute("SELECT relpath FROM images WHERE id=?",(task["image_id"],)).fetchone()[0]
    assert client.get(task["image_url"]).content==path.read_bytes()
    assert env["clients"]["bob"].get(task["image_url"]).status_code==404
    assert env["clients"]["bob"].get(f"/api/tasks/{task['id']}").status_code==404
    assert env["clients"]["bob"].post(f"/api/tasks/{task['id']}/submit",json={"labels":VALID,"revision":0}).status_code==404
    Image.new("L",(16,16),255).save(path)
    assert client.get(task["image_url"]).status_code==409
    assert submit(client,task).status_code==409


def test_admin_scan_boundaries_and_duplicate_import(env):
    admin=env["clients"]["admin"]
    assert admin.post('/api/admin/datasets',json={"name":"outside","path":".."}).status_code==422
    (env["batch"]/'bad.png').write_text('not an image')
    Image.new('I;16',(16,16)).save(env["batch"]/'16bit.tiff')
    result=admin.post('/api/admin/datasets',json={"name":"scan","path":"batch"})
    assert result.status_code==200
    assert result.json()['imported']==12 and result.json()['skipped_count']==2
    assert admin.post('/api/admin/datasets',json={"name":"again","path":"batch"}).status_code==409


def test_user_creation_disable_password_reset_and_logout(env):
    admin=env['clients']['admin'];alice=env['clients']['alice']
    assert admin.post('/api/admin/users',json={"username":"new","display_name":"新标注员","password":PASSWORD}).status_code==200
    assert admin.post('/api/admin/users',json={"username":"new","display_name":"新标注员","password":PASSWORD}).status_code==409
    assert admin.patch('/api/admin/users/2',json={"enabled":False}).status_code==200
    assert alice.get('/api/me').status_code==401
    assert admin.patch('/api/admin/users/2',json={"enabled":True,"password":"replacement-12345"}).status_code==200
    assert alice.post('/api/login',json={"username":"alice","password":PASSWORD}).status_code==401
    assert alice.post('/api/login',json={"username":"alice","password":"replacement-12345"}).status_code==200
    alice.headers['X-CSRF-Token']=alice.get('/api/me').json()['csrf']
    assert alice.post('/api/logout').status_code==200
    assert alice.get('/api/me').status_code==401
    assert admin.patch('/api/admin/users/1',json={"enabled":False}).status_code==404


def test_concurrent_next_does_not_duplicate_assignment(env):
    activate(env)
    client=env['clients']['alice']
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks=list(pool.map(lambda _:next_task(client),range(4)))
    assert len({t['id'] for t in tasks})==1
    with connect(env['db']) as db:
        assert db.execute('SELECT count(*) FROM assignments WHERE user_id=2').fetchone()[0]==12


def test_server_forces_na_for_mixed_layers(env):
    activate(env)
    client=env['clients']['alice'];task=next_task(client)
    result=submit(client,task,{**VALID,'q1':{'a':'k','b':'i'}})
    assert result.status_code==200
    assert result.json()['labels']['q2']==result.json()['labels']['q3']=='n'


def test_shared_optional_api_mode(env):
    activate(env,'shared')
    alice,bob=env['clients']['alice'],env['clients']['bob']
    a,b=next_task(alice),next_task(bob)
    assert a['image_id']!=b['image_id']
    assert env['clients']['admin'].patch('/api/admin/users/2',json={'enabled':False}).status_code==200
    with connect(env['db']) as db:
        assert db.execute('SELECT count(*) FROM assignments WHERE user_id=2').fetchone()[0]==0


def test_csv_escapes_formula_and_only_admin_export(env):
    did=activate(env)
    client=env['clients']['alice'];submit(client,next_task(client))
    with connect(env['db']) as db:
        db.execute("UPDATE users SET display_name='=1+1' WHERE id=2")
    response=env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}')
    assert response.status_code==200 and "'=1+1" in response.text
    assert client.get(f'/api/admin/export?dataset_id={did}').status_code==403


def test_login_throttles_and_cookie_flags(env):
    client=TestClient(env['app'])
    for _ in range(10):
        assert client.post('/api/login',json={'username':'nobody','password':'incorrect'}).status_code==401
    assert client.post('/api/login',json={'username':'nobody','password':'incorrect'}).status_code==429
    response=client.post('/api/login',json={'username':'alice','password':PASSWORD})
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']


def test_empty_dataset_and_security_headers(env):
    client=env['clients']['alice']
    assert next_task(client) is None
    assert client.get('/api/progress').json()['dataset'] is None
    response=client.get('/')
    assert response.status_code==200 and "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/api/me').headers['cache-control']=='no-store'


def test_manual_examples_and_backup(env, tmp_path, monkeypatch):
    from app import backup
    client=env['clients']['alice']
    assert '20261027' in client.get('/api/manual').json()['text']
    assert client.get('/manual/images/Q1/a/R0200.png').status_code==200
    activate(env)
    assert submit(client,next_task(client)).status_code==200
    destination=tmp_path/'snapshot.sqlite3'
    monkeypatch.setenv('CCM_DB',str(env['db']))
    monkeypatch.setattr('sys.argv',['backup',str(destination)])
    backup.main()
    with sqlite3.connect(destination) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM annotations').fetchone()[0]==1
    with pytest.raises(SystemExit):
        backup.main()
