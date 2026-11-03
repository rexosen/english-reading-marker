import json
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from src.repository import ReaderRepository
from src.lan_sync import LanSyncService,connect,snapshot

class LanSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'reader.sqlite3'
        self.repo=ReaderRepository(self.path)
        self.article_id=self.repo.create_article('Original','An online class. Students learn. 😀 Students work.')
        self.server=LanSyncService(self.path)
        port=self.server.start('127.0.0.1',0)
        self.url=f'http://127.0.0.1:{port}'
        code=self.server.new_pairing_code()
        result=self.post('/pair',{'code':code})
        self.token=result['token'];self.instance=result['instance']
        self.article=self.sync()['articles'][0]

    def tearDown(self):
        self.server.stop();self.repo.close();self.temp.cleanup()

    def post(self,path,payload,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        with urlopen(Request(self.url+path,data=json.dumps(payload).encode(),headers=headers),timeout=5) as response:
            return json.load(response)

    def sync(self,ops=None,instance=None):
        return self.post('/sync',{'client_id':'test-phone','instance':instance or self.instance,'operations':ops or []},self.token)

    def op(self,type,**fields):
        return {'id':str(uuid.uuid4()),'type':type,'article_id':self.article['id'],**fields}

    def test_existing_data_retains_ids_and_one_time_pairing(self):
        self.assertEqual(self.repo.get_article(self.article_id)['title'],'Original')
        with self.assertRaises(HTTPError) as failure:self.post('/pair',{'code':''})
        self.assertEqual(failure.exception.code,401);failure.exception.close()
        with self.assertRaises(HTTPError) as failure:self.post('/sync',{'client_id':'other'})
        self.assertEqual(failure.exception.code,401);failure.exception.close()

    def test_offline_operations_retry_without_duplicates(self):
        mark=self.op('underline',start=3,end=9,word='online',active=True)
        word=self.op('vocabulary',start=3,end=9,word='online',definition='在线的')
        for _ in range(3):result=self.sync([mark,word])
        self.assertEqual(len(result['articles'][0]['annotations']),1)
        self.assertEqual(len(result['articles'][0]['vocabulary']),1)
        self.assertEqual(self.repo.list_annotations(self.article_id)[0]['start'],3)
        remove=self.op('underline',start=3,end=9,word='online',active=False)
        self.sync([remove]);self.assertEqual(self.repo.list_annotations(self.article_id),[])

    def test_unicode_offsets_refer_to_exact_occurrence(self):
        text=self.article['text'];start=text.rindex('Students')
        result=self.sync([self.op('underline',start=start,end=start+8,word='Students',active=True)])
        self.assertEqual(result['articles'][0]['annotations'][0]['start'],start)

    def test_concurrent_rename_requires_explicit_resolution(self):
        self.repo.rename_article(self.article_id,'Desktop name')
        rename=self.op('rename',title='Phone name',base_version=1)
        result=self.sync([rename])
        self.assertEqual(result['articles'][0]['title'],'Desktop name')
        self.assertEqual(len(result['conflicts']),1)
        result=self.sync([rename]);self.assertEqual(len(result['conflicts']),1)
        conflict=result['conflicts'][0]
        result=self.sync([self.op('resolve',conflict_id=conflict['id'],choice='mobile',base_version=conflict['title_version'])])
        self.assertEqual(result['articles'][0]['title'],'Phone name')
        self.assertEqual(result['conflicts'],[])

    def test_new_mobile_article_and_mark_import_together(self):
        article_id='mobile:'+str(uuid.uuid4())
        create={'id':str(uuid.uuid4()),'type':'create','article_id':article_id,'title':'Phone article','text':'Phone text.'}
        mark={'id':str(uuid.uuid4()),'type':'underline','article_id':article_id,'start':0,'end':5,'word':'Phone','active':True}
        result=self.sync([create,mark]);result=self.sync([create,mark])
        imported=[a for a in result['articles'] if a['id']==article_id]
        self.assertEqual(len(imported),1);self.assertEqual(len(imported[0]['annotations']),1)

    def test_invalid_location_and_wrong_instance_do_not_write(self):
        bad=self.op('underline',start=3,end=9,word='wrong',active=True)
        result=self.sync([bad]);self.assertIn('error',result['acknowledgements'][0])
        self.assertEqual(self.repo.list_annotations(self.article_id),[])
        with self.assertRaises(HTTPError) as failure:self.sync([self.op('rename',title='Wrong',base_version=1)],'other-instance')
        self.assertEqual(failure.exception.code,409);failure.exception.close()
        self.assertEqual(self.repo.get_article(self.article_id)['title'],'Original')

    def test_desktop_changes_are_visible_and_reading_progress_returns(self):
        self.repo.rename_article(self.article_id,'New title')
        self.repo.add_annotation(self.article_id,3,9,'online')
        result=self.sync([self.op('progress',offset=20)])
        self.assertEqual(result['articles'][0]['title'],'New title')
        self.assertEqual(len(result['articles'][0]['annotations']),1)
        self.assertEqual(self.repo.get_progress(self.article_id),20)

    def test_local_download_page_exposes_only_apk_not_reader_database(self):
        apk=Path(self.temp.name)/'test.apk';apk.write_bytes(b'test-apk')
        self.server.android_apk=apk
        with urlopen(self.url+'/') as response:self.assertIn(b'/android.apk',response.read())
        with urlopen(self.url+'/android.apk') as response:self.assertEqual(response.read(),b'test-apk')
        with self.assertRaises(HTTPError) as failure:urlopen(self.url+'/reader.sqlite3')
        self.assertEqual(failure.exception.code,404);failure.exception.close()
