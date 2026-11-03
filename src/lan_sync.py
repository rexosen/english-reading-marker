"""Authenticated LAN sync. Existing desktop tables retain their IDs and data."""
from __future__ import annotations
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from src.domain import sentence_for_range


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize_sync(path):
    db = connect(path)
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sync_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_articles(article_id INTEGER PRIMARY KEY REFERENCES articles(id),sync_id TEXT UNIQUE NOT NULL,title_version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sync_journal(seq INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_devices(token_hash TEXT PRIMARY KEY,created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_operations(op_id TEXT PRIMARY KEY,result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_conflicts(id TEXT PRIMARY KEY,client_id TEXT NOT NULL,article_id INTEGER NOT NULL,proposed TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reading_progress(article_id INTEGER PRIMARY KEY REFERENCES articles(id),offset INTEGER NOT NULL DEFAULT 0);
        """)
        db.execute("INSERT OR IGNORE INTO sync_settings VALUES ('instance',?)", (str(uuid.uuid4()),))
        from src.study import initialize_study
        initialize_study(db)
        instance = db.execute("SELECT value FROM sync_settings WHERE key='instance'").fetchone()[0]
        db.execute("INSERT OR IGNORE INTO sync_articles(article_id,sync_id) SELECT id,? || ':' || id FROM articles", (instance,))
        db.executescript("""
        CREATE TRIGGER IF NOT EXISTS sync_new_article AFTER INSERT ON articles BEGIN
          INSERT INTO sync_articles(article_id,sync_id) VALUES(NEW.id,(SELECT value FROM sync_settings WHERE key='instance') || ':' || NEW.id);
          INSERT INTO sync_journal(kind) VALUES('article');
        END;
        CREATE TRIGGER IF NOT EXISTS sync_title AFTER UPDATE OF title ON articles WHEN OLD.title != NEW.title BEGIN
          UPDATE sync_articles SET title_version=title_version+1 WHERE article_id=NEW.id;
          INSERT INTO sync_journal(kind) VALUES('article');
        END;
        CREATE TRIGGER IF NOT EXISTS sync_annotation_add AFTER INSERT ON annotations BEGIN INSERT INTO sync_journal(kind) VALUES('annotation'); END;
        CREATE TRIGGER IF NOT EXISTS sync_annotation_remove AFTER DELETE ON annotations BEGIN INSERT INTO sync_journal(kind) VALUES('annotation'); END;
        CREATE TRIGGER IF NOT EXISTS sync_word_add AFTER INSERT ON vocabulary BEGIN INSERT INTO sync_journal(kind) VALUES('vocabulary'); END;
        """)
        db.commit()
    finally:
        db.close()


def revision(db):
    return db.execute("SELECT COALESCE(MAX(seq),0) FROM sync_journal").fetchone()[0]


def snapshot(db, client_id):
    articles = []
    for row in db.execute("SELECT a.*,s.sync_id,s.title_version,COALESCE(p.offset,0) AS progress FROM articles a JOIN sync_articles s ON s.article_id=a.id LEFT JOIN reading_progress p ON p.article_id=a.id ORDER BY a.id DESC"):
        a = dict(row)
        a['local_id'] = a.pop('id')
        a['id'] = a.pop('sync_id')
        a['annotations'] = [dict(r) for r in db.execute('SELECT start,end,word FROM annotations WHERE article_id=? ORDER BY start',(a['local_id'],))]
        a['vocabulary'] = [dict(r) for r in db.execute('SELECT start,end,word,definition,context FROM vocabulary WHERE article_id=? ORDER BY id',(a['local_id'],))]
        del a['local_id']
        articles.append(a)
    conflicts = [dict(r) for r in db.execute('SELECT c.id,s.sync_id AS article_id,c.proposed,a.title AS current_title,s.title_version FROM sync_conflicts c JOIN sync_articles s ON s.article_id=c.article_id JOIN articles a ON a.id=c.article_id WHERE c.client_id=? AND c.resolved=0',(client_id,))]
    from src.study import study_snapshot
    return {'instance':db.execute("SELECT value FROM sync_settings WHERE key='instance'").fetchone()[0], 'revision':revision(db), 'articles':articles, 'conflicts':conflicts, 'study':study_snapshot(db)}


def valid_text(value, name, limit=200000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError(name+'为空或超过长度限制')
    return value.strip()


def apply_operation(db, op, client_id):
    if not isinstance(op,dict): raise ValueError('操作格式错误')
    op_id = valid_text(op.get('id'),'操作编号',100)
    previous = db.execute('SELECT result FROM sync_operations WHERE op_id=?',(op_id,)).fetchone()
    if previous: return json.loads(previous[0])
    kind = op.get('type')
    if kind == 'study':
        from src.study import set_study
        from src.study import _UNSPECIFIED
        stored_key = set_study(db, op.get('key'), op.get('value'), expected=op.get('expected', _UNSPECIFIED))
        result = {'id': op_id, 'ok': True, 'stored_key': stored_key}
        db.execute('INSERT INTO sync_operations VALUES (?,?)', (op_id, json.dumps(result)))
        return result
    article_sync_id = valid_text(op.get('article_id'),'文章编号',120)
    article = db.execute('SELECT a.*,s.title_version FROM articles a JOIN sync_articles s ON s.article_id=a.id WHERE s.sync_id=?',(article_sync_id,)).fetchone()
    if kind == 'create':
        if article is None:
            title=valid_text(op.get('title'),'文章名称',200)
            text=valid_text(op.get('text'),'正文')
            from src.domain import normalize_article_text
            text=normalize_article_text(text)
            cursor=db.execute("INSERT INTO articles(title,text,created_at) VALUES (?,?,datetime('now'))",(title,text))
            db.execute('UPDATE sync_articles SET sync_id=? WHERE article_id=?',(article_sync_id,cursor.lastrowid))
    else:
        if article is None: raise ValueError('文章不存在，请先同步')
        local_id=article['id']
        if kind == 'rename':
            title=valid_text(op.get('title'),'文章名称',200)
            if article['title'] != title:
                if op.get('base_version') != article['title_version'] or db.execute('SELECT 1 FROM sync_conflicts WHERE client_id=? AND article_id=? AND resolved=0',(client_id,local_id)).fetchone():
                    db.execute('INSERT OR IGNORE INTO sync_conflicts(id,client_id,article_id,proposed) VALUES (?,?,?,?)',(op_id,client_id,local_id,title))
                else:
                    db.execute('UPDATE articles SET title=? WHERE id=?',(title,local_id))
        elif kind == 'resolve':
            conflict=db.execute('SELECT * FROM sync_conflicts WHERE id=? AND client_id=? AND article_id=? AND resolved=0',(op.get('conflict_id'),client_id,local_id)).fetchone()
            if conflict:
                if op.get('choice') == 'mobile':
                    if op.get('base_version') != article['title_version']:
                        return {'id':op_id,'retry':True,'error':'名称再次改变，请查看最新名称后选择'}
                    db.execute('UPDATE articles SET title=? WHERE id=?',(conflict['proposed'],local_id))
                elif op.get('choice') != 'computer': raise ValueError('请选择保留哪个名称')
                db.execute('UPDATE sync_conflicts SET resolved=1 WHERE id=?',(conflict['id'],))
        elif kind == 'progress':
            offset=op.get('offset')
            if type(offset) is not int or not 0<=offset<=len(article['text']): raise ValueError('阅读位置无效')
            db.execute('INSERT INTO reading_progress VALUES (?,?) ON CONFLICT(article_id) DO UPDATE SET offset=excluded.offset',(local_id,offset))
        elif kind in ('underline','vocabulary'):
            start,end=op.get('start'),op.get('end')
            if type(start) is not int or type(end) is not int or not 0<=start<end<=len(article['text']): raise ValueError('标记位置无效')
            word=article['text'][start:end]
            if word != op.get('word'): raise ValueError('标记文字与原文位置不符，请重新同步')
            if kind == 'underline':
                if op.get('active') is True:
                    db.execute("INSERT OR IGNORE INTO annotations(article_id,start,end,word,created_at) VALUES(?,?,?,?,datetime('now'))",(local_id,start,end,word))
                elif op.get('active') is False:
                    db.execute('DELETE FROM annotations WHERE article_id=? AND start=? AND end=?',(local_id,start,end))
                else: raise ValueError('划线状态无效')
            else:
                definition=valid_text(op.get('definition'),'释义',20000)
                context=sentence_for_range(article['text'],start,end)
                db.execute("INSERT OR IGNORE INTO vocabulary(article_id,start,end,word,definition,context,created_at) VALUES(?,?,?,?,?,?,datetime('now'))",(local_id,start,end,word,definition,context))
        else: raise ValueError('不支持的操作')
    result={'id':op_id,'ok':True}
    db.execute('INSERT INTO sync_operations VALUES (?,?)',(op_id,json.dumps(result)))
    return result


class LanSyncService:
    def __init__(self, database_path, android_apk=None):
        self.database_path=Path(database_path)
        self.android_apk=Path(android_apk) if android_apk else None
        initialize_sync(self.database_path)
        self.server=None
        self.thread=None
        self.code=''
        self.code_deadline=0
        self.pair_attempts={}
        self.lock=threading.Lock()

    def new_pairing_code(self):
        self.code=f'{secrets.randbelow(1000000):06d}'
        self.code_deadline=time.monotonic()+600
        return self.code

    def start(self, host='0.0.0.0', port=18765):
        if self.server: return self.server.server_port
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def respond(self,status,payload):
                data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                address=ipaddress.ip_address(self.client_address[0])
                if not address.is_private and not address.is_loopback:
                    self.respond(403,{'error':'仅支持局域网'});return
                if self.path=='/android.apk' and owner.android_apk and owner.android_apk.is_file():
                    self.send_response(200)
                    self.send_header('Content-Type','application/vnd.android.package-archive')
                    self.send_header('Content-Length',str(owner.android_apk.stat().st_size))
                    self.send_header('Content-Disposition','attachment; filename="EnglishReadingMarker.apk"')
                    self.end_headers()
                    try:
                        with owner.android_apk.open('rb') as apk:
                            while chunk:=apk.read(65536):self.wfile.write(chunk)
                    except OSError:pass
                    return
                if self.path=='/':
                    body=("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>英语阅读标记器</title><body style='font:18px sans-serif;padding:28px;line-height:1.8'><h2>英语阅读标记器</h2><p>电脑同步服务已运行。</p>"+
                        ("<p><a href='/android.apk'>下载安卓安装包</a></p>" if owner.android_apk and owner.android_apk.is_file() else "")+
                        "<p>安装后，在 App 的“连接电脑”中输入本页地址与电脑上显示的一次性配对码。</p><p>请保持两台设备连接同一个路由器。</p></body>").encode('utf-8')
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                else:self.respond(404,{'error':'页面不存在'})
            def do_POST(self):
                try:
                    address=ipaddress.ip_address(self.client_address[0])
                    if not address.is_private and not address.is_loopback:
                        self.respond(403,{'error':'仅支持局域网'});return
                    length=int(self.headers.get('Content-Length','0'))
                    if length<=0 or length>2000000: raise ValueError('请求长度无效')
                    self.connection.settimeout(15)
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):raise ValueError('请求格式错误')
                    if self.path=='/pair':
                        with owner.lock:
                            now=time.monotonic()
                            recent=[t for t in owner.pair_attempts.get(self.client_address[0],[]) if now-t<60]
                            owner.pair_attempts[self.client_address[0]]=recent+[now]
                            if len(recent)>=10:
                                self.respond(429,{'error':'配对尝试过多，请一分钟后重试'});return
                            if now>owner.code_deadline or not owner.code or not hmac.compare_digest(str(payload.get('code','')),owner.code):
                                self.respond(401,{'error':'配对码错误或已过期'});return
                            token=secrets.token_urlsafe(32)
                            db=connect(owner.database_path)
                            try:
                                with db:db.execute('INSERT INTO sync_devices VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()))
                            finally:db.close()
                            owner.code='';owner.code_deadline=0
                            db=connect(owner.database_path)
                            try:instance=db.execute("SELECT value FROM sync_settings WHERE key='instance'").fetchone()[0]
                            finally:db.close()
                            self.respond(200,{'token':token,'instance':instance});return
                    token=self.headers.get('Authorization','').removeprefix('Bearer ')
                    db=connect(owner.database_path)
                    try:
                        if not db.execute('SELECT 1 FROM sync_devices WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone():
                            self.respond(401,{'error':'请先在电脑上开启配对，再输入配对码'});return
                        if self.path=='/sync':
                            instance=db.execute("SELECT value FROM sync_settings WHERE key='instance'").fetchone()[0]
                            if payload.get('instance') and payload['instance']!=instance:
                                self.respond(409,{'error':'手机数据属于另一台电脑，已阻止修改'});return
                            client_id=valid_text(payload.get('client_id'),'设备编号',100)
                            ops=payload.get('operations',[])
                            if not isinstance(ops,list) or len(ops)>500:raise ValueError('一次最多同步 500 项修改')
                            # Serialize writes and snapshot reads as one transaction.
                            db.execute('BEGIN IMMEDIATE')
                            acknowledgements=[]
                            for op in ops:
                                db.execute('SAVEPOINT operation')
                                try:
                                    acknowledgements.append(apply_operation(db,op,client_id))
                                    db.execute('RELEASE operation')
                                except (ValueError,sqlite3.IntegrityError) as error:
                                    db.execute('ROLLBACK TO operation');db.execute('RELEASE operation')
                                    acknowledgements.append({'id':op.get('id') if isinstance(op,dict) else None,'error':str(error)})
                            result=snapshot(db,client_id)
                            result['acknowledgements']=acknowledgements
                            db.commit();self.respond(200,result)
                        elif self.path=='/translate':
                            from src.dictionary import lookup_chinese,DictionaryError
                            text=valid_text(payload.get('text'),'待翻译内容',20000)
                            try:self.respond(200,{'text':lookup_chinese(text)})
                            except DictionaryError as error:self.respond(502,{'error':str(error)})
                        elif self.path=='/tts':
                            text=valid_text(payload.get('text'),'待朗读内容',600)
                            accent=payload.get('accent') if payload.get('accent') in ('us','uk') else 'us'
                            voice='en-GB-SoniaNeural' if accent=='uk' else 'en-US-AriaNeural'
                            try:
                                import asyncio,edge_tts
                                async def collect():
                                    audio=bytearray()
                                    async for chunk in edge_tts.Communicate(text,voice).stream():
                                        if chunk.get('type')=='audio':audio.extend(chunk['data'])
                                    return bytes(audio)
                                audio=asyncio.run(asyncio.wait_for(collect(),timeout=12))
                                if not audio or len(audio)>512000:raise RuntimeError('语音服务未返回可用音频')
                                self.send_response(200);self.send_header('Content-Type','audio/mpeg');self.send_header('Content-Length',str(len(audio)));self.end_headers();self.wfile.write(audio)
                            except Exception:
                                self.respond(502,{'error':'电脑在线语音暂不可用，可在发音设置里改用系统语音'})
                        else:self.respond(404,{'error':'接口不存在'})
                    finally:db.close()
                except (ValueError,TypeError,KeyError, json.JSONDecodeError) as error:
                    self.respond(400,{'error':str(error)})
                except (OSError,sqlite3.Error):
                    try:self.respond(503,{'error':'同步暂时不可用，请稍后重试'})
                    except OSError:pass
        self.server=ThreadingHTTPServer((host,port),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        return self.server.server_port

    def stop(self):
        if self.server:
            self.server.shutdown();self.server.server_close();self.server=None
        self.code='';self.code_deadline=0

    def addresses(self):
        addresses=set()
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                probe.connect(('192.0.2.1',80));addresses.add(probe.getsockname()[0])
        except OSError:pass
        try:addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:pass
        return [f'http://{ip}:{self.server.server_port}' for ip in sorted(addresses) if ip!='127.0.0.1' and not ip.startswith('169.254.')]
