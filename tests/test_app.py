import csv
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db import connect, initialize, password_hash
from app.main import create_app
from app.rules import MANUAL_VERSION, normalize

PASSWORD = "only-for-test-12345"
VALID = {"q1": {"a": None}, "q2": "a", "q3": "a", "q4": [], "q4_details": {}}


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
    return client.post(f"/api/tasks/{task['id']}/submit",json={"labels":labels,"revision":task["revision"],"manual_version":MANUAL_VERSION})


@pytest.mark.parametrize("q1", [{"b":"i"},{"a":"k","c":"i"},{"d":"k"},{"a":"j","b":"j"}])
def test_mixed_layer_rule(q1):
    result=normalize({**VALID,"q1":q1},True)
    assert result["q2"] == "n" and result["q3"] is None and result["q4"] is None and result["q4_details"] == {}


@pytest.mark.parametrize("labels", [
    {**VALID,"q1":{}}, {**VALID,"q1":{"a":None,"b":"i"}}, {**VALID,"q1":{"a":"z"}},
    {**VALID,"q2":"n"}, {**VALID,"q2":"d"}, {**VALID,"q3":None}, {**VALID,"q3":[]},
    {**VALID,"q3":"n"}, {**VALID,"q3":"d"}, {**VALID,"q3":["a","b"]},
    {**VALID,"q4":["n"]}, {**VALID,"q4":["e"]}, {**VALID,"q4":["a","a"]}, {**VALID,"q4":"a"},
    {**VALID,"q4":["c"]}, {**VALID,"q4_details":{"c":"c1"}},
    {**VALID,"q4":["c"],"q4_details":{"c":["c1","c2"]}},
    {**VALID,"q4":["c"],"q4_details":{"c":"c4"}}, {**VALID,"q4_details":{"e":"e1"}},
    {**VALID,"q3_details":{}},
])
def test_invalid_final_labels(labels):
    with pytest.raises(ValueError):
        normalize(labels,True)


def test_incomplete_drafts_permitted():
    assert normalize({"q1":{"a":None},"q2":None,"q3":None})["q1"] == {"a":None}
    assert normalize({**VALID,"q4":["c"]})["q4_details"] == {"c":None}
    assert normalize(VALID, True) == VALID  # Q4 can be left empty.


def test_auth_and_csrf(env):
    anonymous=TestClient(env["app"])
    assert anonymous.get("/api/history").status_code == 401
    assert anonymous.get("/api/admin/export?dataset_id=1").status_code == 401
    assert anonymous.get("/api/manual").status_code == 404
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


def test_previous_navigation_preserves_order_drafts_and_audit(env):
    activate(env)
    client=env['clients']['alice']
    first=next_task(client)
    with connect(env['db']) as db:
        ids=[r['id'] for r in db.execute('SELECT id FROM assignments WHERE user_id=2 ORDER BY position')]
    assert first['previous_id'] is None and first['next_id']==ids[1]
    assert submit(client,first).status_code==200
    second=next_task(client)
    assert second['previous_id']==first['id'] and second['next_id']==ids[2]
    partial={'q1':{'a':None},'q2':'c','q3':None,'q4':['c'],'q4_details':{'c':None}}
    assert client.put(f"/api/tasks/{second['id']}/draft",json={
        'labels':partial,'revision':second['revision'],'manual_version':MANUAL_VERSION}).status_code==200
    previous=client.get(f"/api/tasks/{second['previous_id']}").json()
    assert previous['submitted'] and previous['labels']==VALID
    assert submit(client,previous,{**VALID,'q2':'b'}).status_code==200
    restored=client.get(f"/api/tasks/{previous['next_id']}").json()
    assert restored['id']==second['id'] and restored['has_draft'] and restored['labels']==partial
    assert client.get('/api/progress').json()['completed']==1
    with connect(env['db']) as db:
        assert db.execute('SELECT count(*) FROM annotation_audit WHERE assignment_id=?',(first['id'],)).fetchone()[0]==2
    assert client.get(f'/api/tasks/{ids[-1]}').json()['next_id'] is None


def test_navigation_is_scoped_to_user_dataset_and_editable_rules(env):
    activate(env)
    alice,bob=env['clients']['alice'],env['clients']['bob']
    first=next_task(alice)
    next_task(bob)
    second=alice.get(f"/api/tasks/{first['next_id']}").json()
    third=alice.get(f"/api/tasks/{second['next_id']}").json()
    with connect(env['db']) as db:
        db.execute('INSERT INTO annotations(assignment_id,labels,manual_version) VALUES(?,?,?)',
                   (second['id'],json.dumps(VALID),'20261029-r3'))
    assert alice.get(f"/api/tasks/{first['id']}").json()['next_id']==third['id']
    assert alice.get(f"/api/tasks/{third['id']}").json()['previous_id']==first['id']
    assert bob.get(f"/api/tasks/{first['id']}").status_code==404
    other=env['root']/'other'; other.mkdir()
    Image.new('L',(16,16),100).save(other/'one.png')
    admin=env['clients']['admin']
    did=admin.post('/api/admin/datasets',json={'name':'Other','path':'other','mode':'independent'}).json()['id']
    assert admin.post(f'/api/admin/datasets/{did}/activate').status_code==200
    only=next_task(alice)
    assert only['previous_id'] is None and only['next_id'] is None
    assert alice.get(f"/api/tasks/{third['id']}").json()['previous_id']==first['id']


def test_completed_queue_can_return_to_last_editable_image(env):
    client=env['clients']['alice']
    assert client.post('/api/tasks/next').json()['previous_id'] is None
    activate(env); next_task(client)
    with connect(env['db']) as db:
        ids=[r['id'] for r in db.execute('SELECT id FROM assignments WHERE user_id=2 ORDER BY position')]
        db.executemany('INSERT INTO annotations(assignment_id,labels,manual_version) VALUES(?,?,?)',
                       [(task_id,json.dumps(VALID),MANUAL_VERSION) for task_id in ids])
    result=client.post('/api/tasks/next').json()
    assert result['task'] is None and result['previous_id']==ids[-1]
    last=client.get(f"/api/tasks/{result['previous_id']}").json()
    assert last['submitted'] and last['previous_id']==ids[-2] and last['next_id'] is None
    with connect(env['db']) as db:
        db.execute('UPDATE annotations SET manual_version=?',('20261029-r3',))
    assert client.post('/api/tasks/next').json()['previous_id'] is None


def test_draft_restoration_revision_conflict_and_audit(env):
    did=activate(env)
    client=env["clients"]["alice"]
    task=next_task(client)
    partial={"q1":{"a":None},"q3":None}
    result=client.put(f"/api/tasks/{task['id']}/draft",json={"labels":partial,"revision":0,"manual_version":MANUAL_VERSION})
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
    assert record["q2"]=="b" and record["q1_a"]=="" and record["q1_layers"]=="a" and record["manual_version"]==MANUAL_VERSION
    assert record["q3"]=="a" and record["q4"]=="" and record["q4_brightness"]==""
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
    assert env["clients"]["bob"].post(f"/api/tasks/{task['id']}/submit",json={"labels":VALID,"revision":0,"manual_version":MANUAL_VERSION}).status_code==404
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
    assert result.json()['labels']['q2']=='n' and result.json()['labels']['q3'] is None


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


def test_backup(env, tmp_path, monkeypatch):
    from app import backup
    client=env['clients']['alice']
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


@pytest.mark.parametrize('layer', ['a','b','c','d'])
def test_single_layer_has_no_area(layer):
    labels=normalize({**VALID,'q1':{layer:'k'}},True)
    assert labels['q1']=={layer:None}
    if layer!='a':
        assert labels['q2']=='n' and labels['q3'] is None


@pytest.mark.parametrize('grade', ['a','b','c'])
def test_q2_three_grades(env, grade):
    assert normalize({**VALID,'q2':grade},True)['q2']==grade
    did=activate(env); client=env['clients']['alice']; task=next_task(client)
    assert submit(client,task,{**VALID,'q2':grade}).status_code==200
    assert client.get(f"/api/tasks/{task['id']}").json()['labels']['q2']==grade
    record=json.loads(env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}&format=jsonl').text)
    assert record['q2']==grade and record['manual_version']==MANUAL_VERSION


@pytest.mark.parametrize('grade', ['ab','bc'])
def test_q2_removed_intermediate_grades_cannot_be_saved(env, grade):
    activate(env); client=env['clients']['alice']; task=next_task(client)
    body={'labels':{**VALID,'q2':grade},'revision':task['revision'],'manual_version':MANUAL_VERSION}
    assert client.put(f"/api/tasks/{task['id']}/draft",json=body).status_code==422
    assert client.post(f"/api/tasks/{task['id']}/submit",json=body).status_code==422
    restored=client.get(f"/api/tasks/{task['id']}").json()
    assert restored['revision']==task['revision'] and not restored['has_draft'] and not restored['submitted']


@pytest.mark.parametrize('immune,brightness', [('a','c1'),('b','c2'),('c','c3')])
def test_immune_grades_and_brightness_round_trip(env, immune, brightness):
    did=activate(env); client=env['clients']['alice']; task=next_task(client)
    labels={**VALID,'q3':immune,'q4':['a','b','c','d'],'q4_details':{'c':brightness}}
    assert client.put(f"/api/tasks/{task['id']}/draft",json={
        'labels':labels,'revision':task['revision'],'manual_version':MANUAL_VERSION}).status_code==200
    draft=next_task(client)
    assert draft['has_draft'] and draft['labels']==labels
    assert submit(client,draft,labels).status_code==200
    restored=client.get(f"/api/tasks/{task['id']}").json()['labels']
    assert restored==labels
    record=json.loads(env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}&format=jsonl').text)
    assert record['q3']==immune and record['q4']=='a;b;c;d' and record['q4_brightness']==brightness
    assert 'q3_overlap' not in record and 'q3_immune' not in record
    audit=json.loads(env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}&format=audit').text)
    assert audit['q4_brightness']==brightness and audit['manual_version']==MANUAL_VERSION
    rows=list(csv.DictReader(io.StringIO(env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}').text.lstrip('\ufeff'))))
    assert rows[0]['q3']==immune and rows[0]['q4_brightness']==brightness


def test_q4_skipped_and_empty_exports(env):
    did=activate(env); client=env['clients']['alice']; admin=env['clients']['admin']
    empty=admin.get(f'/api/admin/export?dataset_id={did}').text
    assert 'q4_brightness' in empty and 'q3_overlap' not in empty
    assert submit(client,next_task(client)).status_code==200
    labels={**VALID,'q1':{'a':'k','b':'i'},'q4':['c'],'q4_details':{'c':'c2'}}
    result=submit(client,next_task(client),labels)
    assert result.status_code==200
    assert result.json()['labels']=={'q1':{'a':'k','b':'i'},'q2':'n','q3':None,'q4':None,'q4_details':{}}
    records=[json.loads(line) for line in admin.get(f'/api/admin/export?dataset_id={did}&format=jsonl').text.splitlines()]
    assert {r['q2'] for r in records}=={'a','n'}
    assert all(r['q4']=='' and r['q4_brightness']=='' for r in records)
    assert next(r for r in records if r['q2']=='n')['q3']==''


def test_rules_and_removed_manual_routes(env):
    client=env['clients']['alice']
    rules=client.get('/api/rules').json()
    assert rules['version']==MANUAL_VERSION=='20261030'
    assert [(o['id'],o['name']) for o in rules['q2']]==[('a','良'),('b','中'),('c','差')]
    assert [(o['id'],o['name']) for o in rules['q3']]==[('a','少'),('b','中'),('c','多')]
    assert '5–20' in rules['q3'][1]['hint'] and '不存在局部区域聚集' in rules['q3'][1]['hint']
    assert '>20' in rules['q3'][2]['hint'] and '>10' in rules['q3'][2]['hint']
    assert [o['id'] for o in rules['q4']]==list('abcd')
    brightness=rules['q4'][2]
    assert [(o['id'],o['name']) for o in brightness['options']]==[('c1','偏亮'),('c2','偏暗'),('c3','显著偏暗')]
    assert brightness['multiple'] is False
    assert all('重叠' not in o['hint'] for o in rules['layers'])
    assert '角落' not in rules['q2'][1]['hint']
    assert client.get('/api/manual').status_code==404
    assert client.get('/manual/images/Q1/a/R0200.png').status_code==404
    page=client.get('/').text
    assert 'manual-nav' not in page and 'manual-dialog' not in page
    assert client.get('/api/health').json()['manual_version']==MANUAL_VERSION


@pytest.mark.parametrize('draft_version', [None,'20261029','20261029-r2','20261029-r3','20261029-r4','20261029-r5'])
def test_old_drafts_are_not_reinterpreted_and_old_clients_cannot_write(env, draft_version):
    activate(env); client=env['clients']['alice']; task=next_task(client)
    old={'q1':{'a':'k'},'q2':'c','q3':'b','q4':['n']} if draft_version is None else {
        'q1':{'a':None},'q2':'ab' if draft_version=='20261029-r4' else 'b','q3':['f'],'q3_details':{'f':'f2'}}
    with connect(env['db']) as db:
        db.execute('UPDATE assignments SET draft=?,draft_version=?,revision=7 WHERE id=?',(json.dumps(old),draft_version,task['id']))
    current=next_task(client)
    assert current['draft_reset'] and not current['has_draft'] and current['revision']==7
    assert current['labels']=={'q1':{},'q2':None,'q3':None,'q4':[],'q4_details':{}}
    for version in (None,'20261027','20261029','20261029-r2','20261029-r3','20261029-r4','20261029-r5'):
        body={'labels':VALID,'revision':7,'manual_version':version}
        assert client.put(f"/api/tasks/{task['id']}/draft",json=body).status_code==409
        assert client.post(f"/api/tasks/{task['id']}/submit",json=body).status_code==409
    assert submit(client,current).status_code==200


def test_legacy_schema_adds_draft_version_without_losing_accounts(tmp_path, hashed):
    from app.db import SCHEMA
    path=tmp_path/'legacy.sqlite3'
    with connect(path) as db:
        db.executescript(SCHEMA.replace('draft_version TEXT, ',''))
        db.execute("INSERT INTO users(username,display_name,password_hash,role) VALUES('kept','kept',?,'admin')",(hashed,))
    initialize(path); initialize(path)
    with connect(path) as db:
        assert 'draft_version' in {r[1] for r in db.execute('PRAGMA table_info(assignments)')}
        assert db.execute('SELECT username FROM users').fetchone()[0]=='kept'


@pytest.mark.parametrize('version,old,expected', [
    ('20261027',{'q1':{'a':'k'},'q2':'c','q3':'d','q4':['b']},{'q2':'c','q3':'d','q4':'b'}),
    ('20261029',{'q1':{'a':None},'q2':'b','q3':['e','f'],'q3_details':{'e':['e1','e2'],'f':'f2'}},
     {'q2':'b','q3':'e;f','q3_overlap':'e1;e2','q3_immune':'f2'}),
    ('20261029-r2',{'q1':{'a':None},'q2':'b','q3':['e','f'],'q3_details':{'e':['e1','e2'],'f':'f2'}},
     {'q2':'b','q3':'e;f','q3_overlap':'e1;e2','q3_immune':'f2'}),
    ('20261029-r3',{'q1':{'a':None},'q2':'b','q3':['e','f'],'q3_details':{'e':['e1','e2'],'f':'f3'}},
     {'q2':'b','q3':'e;f','q3_overlap':'e1;e2','q3_immune':'f3'}),
    ('20261029-r4',{'q1':{'a':None},'q2':'ab','q3':['e','f'],'q3_details':{'e':['e1','e2'],'f':'f3'}},
     {'q2':'ab','q3':'e;f','q3_overlap':'e1;e2','q3_immune':'f3'}),
    ('20261029-r4',{'q1':{'a':None},'q2':'bc','q3':['n'],'q3_details':{}},
     {'q2':'bc','q3':'n','q3_overlap':'','q3_immune':''}),
    ('20261029-r5',{'q1':{'a':None},'q2':'b','q3':['e','f'],'q3_details':{'e':['e1','e2'],'f':'f3'}},
     {'q2':'b','q3':'e;f','q3_overlap':'e1;e2','q3_immune':'f3'}),
])
def test_legacy_formal_record_is_preserved_for_export(env, version, old, expected):
    did=activate(env); client=env['clients']['alice']; task=next_task(client)
    with connect(env['db']) as db:
        db.execute('INSERT INTO annotations(assignment_id,labels,manual_version) VALUES(?,?,?)',(task['id'],json.dumps(old),version))
        db.execute('INSERT INTO annotation_audit(assignment_id,labels,manual_version,revision) VALUES(?,?,?,?)',(task['id'],json.dumps(old),version,0))
    assert client.get(f"/api/tasks/{task['id']}").status_code==409
    assert submit(client,task).status_code==409
    assert submit(client,next_task(client)).status_code==200
    records=[json.loads(line) for line in env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}&format=jsonl').text.splitlines()]
    legacy=next(r for r in records if r['manual_version']==version)
    assert {key:legacy[key] for key in expected}==expected
    if 'q3_details' in old:
        assert 'q4' not in legacy
    audit=[json.loads(line) for line in env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}&format=audit').text.splitlines()]
    legacy_audit=next(r for r in audit if r['manual_version']==version)
    assert {key:legacy_audit[key] for key in expected}==expected
    assert env['clients']['admin'].get(f'/api/admin/export?dataset_id={did}').status_code==200
