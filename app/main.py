import csv
import hashlib
import io
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from .db import connect, default_db, initialize, password_hash, verify_password
from .rules import AREAS, LAYERS, MANUAL_VERSION, Q2, Q3, Q4, normalize

BASE = Path(__file__).resolve().parents[1]
EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
EMPTY = {"q1": {}, "q2": None, "q3": None, "q4": [], "q4_details": {}}


def create_app(db_path=None, image_root=None, secure_cookie=None):
    app = FastAPI(title="CCM 图像质量标注", docs_url=None, redoc_url=None, openapi_url=None)
    database = str(db_path or default_db())
    initialize(database)
    allowed_root = Path(image_root or os.getenv("CCM_IMAGE_ROOT", str(BASE / "data" / "images"))).resolve()
    if image_root is None and not os.getenv("CCM_IMAGE_ROOT"):
        allowed_root.mkdir(parents=True, exist_ok=True)
    secure = secure_cookie if secure_cookie is not None else os.getenv("CCM_SECURE_COOKIE", "0") == "1"
    dummy_hash = password_hash(secrets.token_urlsafe(24))

    @app.middleware("http")
    async def security(request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected = os.getenv("CCM_PUBLIC_ORIGIN")
            if origin and (origin != expected if expected else urlsplit(origin).netloc != request.headers.get("host")):
                return Response("Cross-origin request denied", status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return Response("Cross-site request denied", status_code=403)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return Response("Invalid Content-Length", status_code=400)
            if length > 32768:
                return Response("Request too large", status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith("/api") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    def user(request: Request):
        digest = hashlib.sha256(request.cookies.get("ccm_session", "").encode()).hexdigest()
        with connect(database) as db:
            row = db.execute("SELECT u.*,s.csrf FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.enabled=1", (digest, time.time())).fetchone()
        if not row:
            raise HTTPException(401, "登录已过期，请重新登录")
        if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), row["csrf"]):
            raise HTTPException(403, "请求校验失败，请刷新页面")
        return dict(row)

    def admin(current=Depends(user)):
        if current["role"] != "admin":
            raise HTTPException(403, "仅管理员可执行此操作")
        return current

    def image_path(row, check_hash=False):
        root = Path(row["root"]).resolve()
        path = (root / row["relpath"]).resolve()
        if not root.is_relative_to(allowed_root) or not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(409, "图像源文件不可用，请联系管理员")
        if check_hash and hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise HTTPException(409, "图像内容已变更，已阻止保存；请联系管理员建立新数据集")
        return path

    def assignment(db, assignment_id, user_id):
        row = db.execute("""SELECT a.*,i.dataset_id,i.width,i.height,i.relpath,i.sha256,d.root,d.name,
            n.labels,n.updated_at,n.manual_version AS annotation_version FROM assignments a JOIN images i ON a.image_id=i.id JOIN datasets d ON d.id=i.dataset_id
            LEFT JOIN annotations n ON n.assignment_id=a.id WHERE a.id=? AND a.user_id=?""", (assignment_id,user_id)).fetchone()
        if not row:
            raise HTTPException(404, "任务不存在或无权访问")
        return row

    def adjacent_task_id(db, user_id, dataset_id, position=None, forward=False):
        comparison, order = (">", "ASC") if forward else ("<", "DESC")
        params = [user_id, dataset_id, MANUAL_VERSION]
        boundary = ""
        if position is not None:
            boundary = f"AND a.position {comparison} ?"
            params.append(position)
        row = db.execute(f"""SELECT a.id FROM assignments a JOIN images i ON i.id=a.image_id
            LEFT JOIN annotations n ON n.assignment_id=a.id
            WHERE a.user_id=? AND i.dataset_id=? AND (n.assignment_id IS NULL OR n.manual_version=?)
            {boundary} ORDER BY a.position {order},a.id {order} LIMIT 1""", params).fetchone()
        return row["id"] if row else None

    def task(db, row):
        if row["labels"] and row["annotation_version"] != MANUAL_VERSION:
            raise HTTPException(409, "旧版正式记录保留供导出，不能用新版规则编辑")
        draft = row["draft"] if row["draft_version"] == MANUAL_VERSION else None
        return {"id": row["id"], "image_id": row["image_id"], "dataset_id": row["dataset_id"], "dataset_name": row["name"],
                "width": row["width"], "height": row["height"], "revision": row["revision"], "submitted": bool(row["labels"]),
                "manual_version": MANUAL_VERSION, "draft_reset": bool(row["draft"] and not draft),
                "has_draft": bool(draft), "labels": json.loads(draft or row["labels"] or json.dumps(EMPTY)),
                "previous_id": adjacent_task_id(db,row["user_id"],row["dataset_id"],row["position"]),
                "next_id": adjacent_task_id(db,row["user_id"],row["dataset_id"],row["position"],forward=True),
                "image_url": f"/api/tasks/{row['id']}/image"}

    @app.get("/api/health")
    def health():
        with connect(database) as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "manual_version": MANUAL_VERSION}

    @app.post("/api/login")
    def login(body: dict, request: Request):
        username = str(body.get("username", "")).strip()[:40]
        ip = request.client.host if request.client else "local"
        buckets = [(f"user:{username}", 10), (f"ip:{ip}", 80)]
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE expires<?", (time.time(),))
            for bucket, limit in buckets:
                record = db.execute("SELECT attempts FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()
                if record and record[0] >= limit:
                    raise HTTPException(429, "登录尝试过多，请 15 分钟后重试")
                db.execute("INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1", (bucket,time.time()+900))
            row = db.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
        valid = verify_password(body.get("password", ""), row["password_hash"] if row else dummy_hash)
        if not row or not valid:
            raise HTTPException(401, "账号或密码错误")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with connect(database) as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("DELETE FROM login_attempts WHERE bucket=?", (f"user:{username}",))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(),row["id"],csrf,time.time()+43200))
        response = Response(content=json.dumps({"ok": True}), media_type="application/json")
        response.set_cookie("ccm_session", token, httponly=True, secure=secure, samesite="strict", max_age=43200, path="/")
        return response

    @app.post("/api/logout")
    def logout(request: Request, current=Depends(user)):
        with connect(database) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(request.cookies["ccm_session"].encode()).hexdigest(),))
        response = Response(content='{"ok":true}', media_type="application/json")
        response.delete_cookie("ccm_session", path="/")
        return response

    @app.get("/api/me")
    def me(current=Depends(user)):
        return {k: current[k] for k in ("id", "username", "display_name", "role", "csrf")}

    @app.get("/api/rules")
    def rules(current=Depends(user)):
        return {"version": MANUAL_VERSION, "layers": LAYERS, "areas": AREAS, "q2": Q2, "q3": Q3, "q4": Q4}

    @app.get("/api/progress")
    def progress(current=Depends(user)):
        with connect(database) as db:
            ds = db.execute("SELECT id,name,mode FROM datasets WHERE active=1").fetchone()
            if not ds:
                return {"dataset": None, "total": 0, "completed": 0, "team_completed": 0}
            total = db.execute("SELECT count(*) FROM images WHERE dataset_id=?", (ds["id"],)).fetchone()[0]
            rows = db.execute("SELECT a.user_id FROM annotations n JOIN assignments a ON n.assignment_id=a.id JOIN images i ON i.id=a.image_id WHERE i.dataset_id=?", (ds["id"],)).fetchall()
            return {"dataset": dict(ds), "total": total, "completed": sum(r[0] == current["id"] for r in rows), "team_completed": len(rows)}

    @app.post("/api/tasks/next")
    def next_task(current=Depends(user)):
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            ds = db.execute("SELECT * FROM datasets WHERE active=1").fetchone()
            if not ds:
                return {"task": None, "previous_id": None, "reason": "管理员尚未启用图像集"}
            uid, did = current["id"], ds["id"]
            if ds["mode"] == "independent":
                ids = [r[0] for r in db.execute("SELECT id FROM images WHERE dataset_id=? AND id NOT IN (SELECT image_id FROM assignments WHERE user_id=?)", (did,uid))]
                secrets.SystemRandom().shuffle(ids)
                offset = db.execute("SELECT coalesce(max(position),0) FROM assignments WHERE user_id=?", (uid,)).fetchone()[0]
                db.executemany("INSERT INTO assignments(user_id,image_id,position) VALUES(?,?,?)", [(uid,i,offset+p+1) for p,i in enumerate(ids)])
            pending = db.execute("SELECT a.id FROM assignments a JOIN images i ON a.image_id=i.id LEFT JOIN annotations n ON n.assignment_id=a.id WHERE a.user_id=? AND i.dataset_id=? AND n.assignment_id IS NULL ORDER BY a.position LIMIT 1", (uid,did)).fetchone()
            if not pending and ds["mode"] == "shared":
                candidate = db.execute("SELECT id FROM images WHERE dataset_id=? AND id NOT IN (SELECT image_id FROM assignments) ORDER BY random() LIMIT 1", (did,)).fetchone()
                if candidate:
                    cursor = db.execute("INSERT INTO assignments(user_id,image_id,position) VALUES(?,?,?)", (uid,candidate[0],candidate[0]))
                    pending = (cursor.lastrowid,)
            return {"task": task(db,assignment(db,pending[0],uid)) if pending else None,
                    "previous_id": None if pending else adjacent_task_id(db,uid,did),
                    "reason": "当前图像集已无待标注图像"}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: int, current=Depends(user)):
        with connect(database) as db:
            return task(db, assignment(db, task_id, current["id"]))

    @app.get("/api/tasks/{task_id}/image")
    def get_image(task_id: int, current=Depends(user)):
        with connect(database) as db:
            row = assignment(db,task_id,current["id"])
        path = image_path(row, True)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return FileResponse(path)
        with Image.open(path) as picture:
            buffer = io.BytesIO()
            picture.save(buffer, "PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    def save(task_id, body, current, final):
        if body.get("manual_version") != MANUAL_VERSION:
            raise HTTPException(409, "标注规则已更新，请刷新页面后重新填写")
        try:
            labels = normalize(body.get("labels"), final)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            row = assignment(db,task_id,current["id"])
            if row["labels"] and row["annotation_version"] != MANUAL_VERSION:
                raise HTTPException(409, "旧版正式记录保留供导出，不能用新版规则编辑")
            if body.get("revision") != row["revision"]:
                raise HTTPException(409, "此图像已在其他页面修改，请刷新后重试")
            image_path(row, True)
            data = json.dumps(labels, ensure_ascii=False)
            revision = row["revision"] + 1
            db.execute("UPDATE assignments SET draft=?,draft_version=?,revision=? WHERE id=?", (None if final else data,None if final else MANUAL_VERSION,revision,task_id))
            if final:
                db.execute("INSERT INTO annotations(assignment_id,labels,manual_version) VALUES(?,?,?) ON CONFLICT(assignment_id) DO UPDATE SET labels=excluded.labels,manual_version=excluded.manual_version,updated_at=CURRENT_TIMESTAMP", (task_id,data,MANUAL_VERSION))
                db.execute("INSERT INTO annotation_audit(assignment_id,labels,manual_version,revision) VALUES(?,?,?,?)", (task_id,data,MANUAL_VERSION,revision))
        return {"ok": True, "revision": revision, "labels": labels}

    @app.put("/api/tasks/{task_id}/draft")
    def draft(task_id: int, body: dict, current=Depends(user)):
        return save(task_id,body,current,False)

    @app.post("/api/tasks/{task_id}/submit")
    def submit(task_id: int, body: dict, current=Depends(user)):
        return save(task_id,body,current,True)

    @app.get("/api/history")
    def history(current=Depends(user)):
        with connect(database) as db:
            rows = db.execute("SELECT a.id,a.image_id,d.name AS dataset_name,n.updated_at FROM annotations n JOIN assignments a ON n.assignment_id=a.id JOIN images i ON i.id=a.image_id JOIN datasets d ON d.id=i.dataset_id WHERE a.user_id=? ORDER BY n.updated_at DESC,a.id DESC LIMIT 100", (current["id"],)).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/admin/overview")
    def overview(current=Depends(admin)):
        with connect(database) as db:
            datasets = [dict(r) for r in db.execute("SELECT d.*,(SELECT count(*) FROM images i WHERE i.dataset_id=d.id) AS count,(SELECT count(*) FROM annotations n JOIN assignments a ON a.id=n.assignment_id JOIN images i ON i.id=a.image_id WHERE i.dataset_id=d.id) AS completed FROM datasets d ORDER BY d.id DESC")]
            users = [dict(r) for r in db.execute("SELECT u.id,u.username,u.display_name,u.role,u.enabled,(SELECT count(*) FROM annotations n JOIN assignments a ON a.id=n.assignment_id WHERE a.user_id=u.id) AS completed FROM users u ORDER BY u.id")]
        return {"image_root": str(allowed_root), "datasets": datasets, "users": users}

    @app.post("/api/admin/users")
    def add_user(body: dict, current=Depends(admin)):
        username = str(body.get("username", "")).strip()
        name = str(body.get("display_name", "")).strip()
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{2,40}", username) or not 1 <= len(name) <= 40:
            raise HTTPException(422, "用户名须为 2–40 位字母/数字/_.-；姓名为 1–40 字符")
        try:
            hashed = password_hash(body.get("password"))
        except ValueError as error:
            raise HTTPException(422,str(error)) from error
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise HTTPException(409, "用户名已存在")
            db.execute("INSERT INTO users(username,display_name,password_hash,role) VALUES(?,?,?,'annotator')", (username,name,hashed))
        return {"ok": True}

    @app.patch("/api/admin/users/{user_id}")
    def update_user(user_id: int, body: dict, current=Depends(admin)):
        with connect(database) as db:
            row = db.execute("SELECT * FROM users WHERE id=? AND role='annotator'", (user_id,)).fetchone()
            if not row:
                raise HTTPException(404, "标注员不存在")
            if "enabled" in body:
                if type(body["enabled"]) is not bool:
                    raise HTTPException(422, "账号状态无效")
                db.execute("UPDATE users SET enabled=? WHERE id=?", (int(body["enabled"]),user_id))
                if not body["enabled"]:
                    # Shared pending tasks return to the pool, finalized work is preserved.
                    db.execute("DELETE FROM assignments WHERE user_id=? AND id NOT IN (SELECT assignment_id FROM annotations) AND image_id IN (SELECT i.id FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE d.mode='shared')", (user_id,))
            if "password" in body:
                try:
                    hashed = password_hash(body["password"])
                except ValueError as error:
                    raise HTTPException(422,str(error)) from error
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed,user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return {"ok": True}

    @app.post("/api/admin/datasets")
    def add_dataset(body: dict, current=Depends(admin)):
        folder = Path(str(body.get("path", ""))).expanduser()
        folder = (allowed_root / folder).resolve() if not folder.is_absolute() else folder.resolve()
        name, mode = str(body.get("name", "")).strip(), body.get("mode", "independent")
        if not folder.is_relative_to(allowed_root) or not folder.is_dir():
            raise HTTPException(422, "目录必须存在且位于允许的图像根目录内")
        if not 1 <= len(name) <= 80 or mode not in {"independent", "shared"}:
            raise HTTPException(422, "数据集名称或分配方式无效")
        with connect(database) as db:
            if db.execute("SELECT 1 FROM datasets WHERE root=?", (str(folder),)).fetchone():
                raise HTTPException(409, "此目录已导入；请使用原数据集，新增批次请指定新目录")
        records, skipped = [], []
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in EXTENSIONS or not path.is_file():
                continue
            if not path.resolve().is_relative_to(folder):
                skipped.append({"file": str(path.relative_to(folder)), "reason": "符号链接指向目录外"})
                continue
            try:
                with Image.open(path) as picture:
                    if picture.mode not in {"L", "RGB", "RGBA", "P", "1"} or getattr(picture,"n_frames",1) != 1:
                        raise ValueError("只支持单帧 8 位图像；高位深或多帧图像须预先确认显示规则")
                    width, height = picture.size
                    picture.verify()
                records.append((str(path.relative_to(folder)),hashlib.sha256(path.read_bytes()).hexdigest(),width,height))
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
                skipped.append({"file": str(path.relative_to(folder)), "reason": str(error)})
        if not records:
            raise HTTPException(422, {"message": "目录中没有可导入的有效图像", "skipped": skipped[:50]})
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM datasets WHERE root=?", (str(folder),)).fetchone():
                raise HTTPException(409, "此目录已由另一位管理员导入")
            cursor = db.execute("INSERT INTO datasets(name,root,mode) VALUES(?,?,?)", (name,str(folder),mode))
            did = cursor.lastrowid
            db.executemany("INSERT INTO images(dataset_id,relpath,sha256,width,height) VALUES(?,?,?,?,?)", [(did,*r) for r in records])
        return {"id": did, "imported": len(records), "skipped_count": len(skipped), "skipped": skipped[:50]}

    @app.post("/api/admin/datasets/{dataset_id}/activate")
    def activate(dataset_id: int, current=Depends(admin)):
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM datasets WHERE id=?", (dataset_id,)).fetchone():
                raise HTTPException(404, "数据集不存在")
            db.execute("UPDATE datasets SET active=0")
            db.execute("UPDATE datasets SET active=1 WHERE id=?", (dataset_id,))
        return {"ok": True}

    @app.get("/api/admin/export")
    def export(dataset_id: int, format: str = "csv", current=Depends(admin)):
        if format not in {"csv", "jsonl", "audit"}:
            raise HTTPException(422, "导出格式无效")
        with connect(database) as db:
            table = "annotation_audit" if format == "audit" else "annotations"
            extra = "n.revision,n.created_at" if format == "audit" else "n.submitted_at,n.updated_at"
            rows = db.execute(f"SELECT d.name AS dataset,u.username,u.display_name,i.id AS image_id,i.relpath,i.sha256,a.position AS presentation_order,n.labels,n.manual_version,{extra} FROM {table} n JOIN assignments a ON a.id=n.assignment_id JOIN users u ON u.id=a.user_id JOIN images i ON i.id=a.image_id JOIN datasets d ON d.id=i.dataset_id WHERE d.id=? ORDER BY u.id,i.id", (dataset_id,)).fetchall()
        data = []
        for row in rows:
            record = dict(row)
            labels = json.loads(record.pop("labels"))
            record["q1_layers"] = ";".join(sorted(labels["q1"]))
            record.update({f"q1_{k}": labels["q1"].get(k) or "" for k in "abcd"})
            record["q2"] = labels["q2"]
            record["q3"] = ";".join(labels["q3"]) if isinstance(labels["q3"], list) else labels["q3"] or ""
            if "q4_details" in labels:
                record["q4"] = ";".join(labels["q4"] or [])
                record["q4_brightness"] = labels["q4_details"].get("c") or ""
            elif "q3_details" in labels:
                # Three-question revisions retain their own grade/threshold meanings.
                record["q3_overlap"] = ";".join(labels["q3_details"].get("e", []))
                record["q3_immune"] = labels["q3_details"].get("f") or ""
            else:
                # Keep legacy exports without reinterpreting their different Q2/Q3 codes.
                record["q4"] = ";".join(labels.get("q4", []))
            data.append(record)
        if format == "csv":
            stream = io.StringIO(newline="")
            fields = list(dict.fromkeys(k for record in data for k in record)) if data else ["dataset","username","display_name","image_id","relpath","sha256","presentation_order","manual_version","submitted_at","updated_at","q1_layers","q1_a","q1_b","q1_c","q1_d","q2","q3","q4","q4_brightness"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            # Spreadsheet formula injection protection for user-controlled text.
            for record in data:
                writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")) else v for k,v in record.items()})
            content = "\ufeff" + stream.getvalue()
        else:
            content = "".join(json.dumps(r,ensure_ascii=False)+"\n" for r in data)
        suffix = "csv" if format == "csv" else "jsonl"
        return Response(content, media_type="text/csv" if format == "csv" else "application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="ccm-{dataset_id}-{format}.{suffix}"'})

    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(BASE / "static" / "index.html")

    return app


app = create_app()
