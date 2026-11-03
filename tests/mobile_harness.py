import json,tempfile,threading,time
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from src.repository import ReaderRepository
from src.lan_sync import LanSyncService
root=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as folder:
    repo=ReaderRepository(Path(folder)/'test.sqlite3')
    repo.create_article('Test article','Online classes help students. 😀 Students learn.\n\nThey are not designed for students to interact with the material in depth but designed to be graded easily to accommodate such a large number of students.')
    service=LanSyncService(repo.database_path);port=service.start('127.0.0.1',0);code=service.new_pairing_code()
    class Static(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root/'android/app/src/main/assets'),**kwargs)
        def log_message(self,*args):pass
    static=ThreadingHTTPServer(('127.0.0.1',0),Static)
    threading.Thread(target=static.serve_forever,daemon=True).start()
    print(json.dumps({'port':port,'code':code,'staticPort':static.server_port}),flush=True)
    try:
        while True:time.sleep(1)
    finally:service.stop();static.shutdown();repo.close()
