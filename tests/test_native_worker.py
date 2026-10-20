import base64
import copy
import datetime as dt
import hashlib
import io
import json
import unittest

from PIL import Image
from scheduler.native_worker import IST, NativeFailure, advance, binding, verify_package


def package():
    image = io.BytesIO()
    Image.new('RGB', (1080, 1350)).save(image, format='PNG')
    data = image.getvalue()
    content = {'headline':'Reviewed headline','caption':'Reviewed caption','claims':[{'text':'A reviewed fact','source_ids':['source'],'support_note':'Primary source establishes this fact'}],'sources':[{'id':'source','url':'https://example.org/primary','checked_at':'2026-10-13T10:00:00+05:30'}],'platforms':['facebook','instagram'],'imageMimeType':'image/png','imageSha256':hashlib.sha256(data).hexdigest()}
    digest=hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {**{k:content[k] for k in ('headline','caption','claims','sources','platforms')},'externalId':'reviewed-fixture','contentHash':digest,'proposedSchedule':'2099-10-13T19:30:00+05:30','scheduleTimezone':'Asia/Kolkata','image':{'mimeType':'image/png','width':1080,'height':1350,'data':base64.b64encode(data).decode()},'nativeHandoff':None}


def checkpoint(packet,state='reserved'):
    value={'state':state,'content_hash':packet['contentHash'],'scheduled_at':binding(packet)['scheduled_at'],'platforms':packet['platforms'],'receipts':{},'reserved_at':'2026-10-13T10:00:00+05:30'}
    if state=='submitting':value['submission_started_at']='2026-10-13T10:01:00+05:30'
    return value


class Driver:
    def __init__(self,packet,observations=None):
        self.packet=packet;self.observations=observations or [{}];self.submits=0;self.events=[];self.inspect_expectations=[]
    def proof(self,packet,image):
        return {**binding(packet),'caption':packet['caption'],'image_sha256':hashlib.sha256(image).hexdigest(),'timezone':'Asia/Kolkata','story':False,'boost':False}
    def prepare(self,packet,image):
        self.events.append('prepare');return self.proof(packet,image)
    def prepared(self,packet):return self.proof(packet,verify_package(packet))
    def submit(self):self.events.append('submit');self.submits+=1
    def inspect(self,packet,*,expect_existing=None):
        self.inspect_expectations.append(expect_existing)
        return self.observations.pop(0) if self.observations else {}


def receipts(packet,platforms=None):
    return {p:{'platform':p,'schedule_id':str(i+100),'scheduled_at':binding(packet)['scheduled_at'],'content_hash':packet['contentHash'],'planner_url':'https://business.facebook.com/latest/content_calendar','checked_at':dt.datetime.now(IST).isoformat()} for i,p in enumerate(platforms or packet['platforms'])}


class NativeWorkerTests(unittest.TestCase):
    def setUp(self):self.packet=package();self.now=dt.datetime.now(IST)
    def test_package_binds_caption_platforms_and_original_image(self):
        self.assertTrue(verify_package(self.packet))
        for changes in [{'caption':'Changed caption'},{'platforms':['facebook']},{'scheduleTimezone':'UTC'}]:
            with self.assertRaises(NativeFailure):verify_package({**self.packet,**changes})
        altered=copy.deepcopy(self.packet);altered['image']['width']=1122
        with self.assertRaises(NativeFailure):verify_package(altered)
    def test_reservation_dispatch_precedes_any_browser_upload(self):
        driver=Driver(self.packet);state={};saved=[];calls=[]
        result=advance(self.packet,state,driver,lambda *args:calls.append(args),lambda s:saved.append(copy.deepcopy(s)),lambda:self.packet,self.now)
        self.assertEqual(result,'reserved');self.assertEqual(calls,[('reserve','reviewed-fixture')]);self.assertEqual(saved[0]['phase'],'reserve_intent');self.assertEqual(driver.events,[])
    def test_expired_and_near_slots_never_dispatch(self):
        for minutes in [-1,5]:
            self.packet['proposedSchedule']=(self.now+dt.timedelta(minutes=minutes)).isoformat()
            calls=[]
            with self.assertRaisesRegex(NativeFailure,'slot_too_close'):advance(self.packet,{},Driver(self.packet),lambda *x:calls.append(x),lambda s:None,lambda:self.packet,self.now)
            self.assertEqual(calls,[])
    def test_matching_prepared_post_submits_once_after_durable_intent(self):
        self.packet['nativeHandoff']=checkpoint(self.packet)
        state={'binding':binding(self.packet),'phase':'reserved'};saved=[];calls=[]
        driver=Driver(self.packet,[{},receipts(self.packet)])
        def persist(s):saved.append(copy.deepcopy(s))
        def workflow(action,item,receipt=None):
            calls.append(action)
            if action=='begin':self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        def submit():
            self.assertEqual(saved[-1]['phase'],'submission_intent');driver.submits+=1
        driver.submit=submit
        self.assertEqual(advance(copy.deepcopy(self.packet),state,driver,workflow,persist,lambda:copy.deepcopy(self.packet),self.now),'scheduled')
        self.assertEqual(driver.submits,1);self.assertEqual(calls,['begin','receipt','receipt']);self.assertEqual(state['phase'],'scheduled')
    def test_restart_after_submission_never_clicks_schedule_again(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        state={'binding':binding(self.packet),'phase':'submission_intent'}
        driver=Driver(self.packet,[receipts(self.packet)]);calls=[]
        advance(self.packet,state,driver,lambda *x:calls.append(x),lambda s:None,lambda:self.packet,self.now)
        self.assertEqual(driver.submits,0);self.assertEqual([x[0] for x in calls],['receipt','receipt'])
        self.assertEqual(driver.inspect_expectations,[None])
    def test_unknown_submission_remains_blocked(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        driver=Driver(self.packet);calls=[]
        with self.assertRaisesRegex(NativeFailure,'native_submission_unconfirmed'):advance(self.packet,{},driver,lambda *x:calls.append(x),lambda s:None,lambda:self.packet,self.now)
        self.assertEqual(driver.submits,0);self.assertEqual(calls,[])
    def test_partial_success_records_only_observed_platform_and_never_resubmits(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        driver=Driver(self.packet,[receipts(self.packet,['facebook'])]);calls=[]
        with self.assertRaisesRegex(NativeFailure,'partial_native_submission'):advance(self.packet,{},driver,lambda *x:calls.append(x),lambda s:None,lambda:self.packet,self.now)
        self.assertEqual(driver.submits,0);self.assertEqual(len(calls),1);self.assertEqual(calls[0][2]['platform'],'facebook')
    def test_changed_approval_before_begin_never_submits(self):
        self.packet['nativeHandoff']=checkpoint(self.packet);state={'binding':binding(self.packet),'phase':'reserved'}
        changed=copy.deepcopy(self.packet);changed['proposedSchedule']='2099-10-14T19:30:00+05:30';driver=Driver(self.packet);calls=[]
        with self.assertRaisesRegex(NativeFailure,'approval_changed'):advance(self.packet,state,driver,lambda *x:calls.append(x),lambda s:None,lambda:changed,self.now)
        self.assertEqual(driver.submits,0);self.assertEqual(calls,[])
    def test_changed_approval_after_begin_never_submits(self):
        self.packet['nativeHandoff']=checkpoint(self.packet);state={'binding':binding(self.packet),'phase':'reserved'};driver=Driver(self.packet)
        def workflow(*args):
            self.packet['nativeHandoff']=checkpoint(self.packet,'submitting');self.packet['proposedSchedule']='2099-10-14T19:30:00+05:30'
        with self.assertRaisesRegex(NativeFailure,'checkpoint_unconfirmed'):advance(copy.deepcopy(self.packet),state,driver,workflow,lambda s:None,lambda:copy.deepcopy(self.packet),self.now)
        self.assertEqual(driver.submits,0)
    def test_existing_schedule_or_foreign_reservation_does_not_submit(self):
        self.packet['nativeHandoff']=checkpoint(self.packet)
        for state,observations in [({},[{}]),({'binding':binding(self.packet),'phase':'reserved'},[receipts(self.packet)])]:
            driver=Driver(self.packet,observations);calls=[]
            with self.assertRaises(NativeFailure):advance(self.packet,state,driver,lambda *x:calls.append(x),lambda s:None,lambda:self.packet,self.now)
            self.assertEqual(driver.submits,0);self.assertEqual(calls,[])
    def test_workflow_failure_keeps_intent_and_prevents_blind_replay(self):
        state={};driver=Driver(self.packet)
        def fail(*args):raise NativeFailure('dispatch_ambiguous')
        with self.assertRaises(NativeFailure):advance(self.packet,state,driver,fail,lambda s:None,lambda:self.packet,self.now)
        self.assertEqual(state['phase'],'reserve_intent')
        with self.assertRaisesRegex(NativeFailure,'reconciliation'):advance(self.packet,state,driver,fail,lambda s:None,lambda:self.packet,self.now)
        self.assertEqual(driver.submits,0)
    def test_saved_schedule_requires_live_matching_planner_entries(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        observed=receipts(self.packet)
        self.packet['nativeHandoff'].update(state='scheduled',receipts=observed)
        for found in [{},receipts(self.packet,['facebook'])]:
            with self.assertRaisesRegex(NativeFailure,'not_visible'):advance(self.packet,{},Driver(self.packet,[found]),lambda *x:None,lambda s:None,lambda:self.packet,dt.datetime.now(IST))
        self.assertEqual(advance(self.packet,{},Driver(self.packet,[observed]),lambda *x:None,lambda s:None,lambda:self.packet,dt.datetime.now(IST)),'scheduled')
    def test_receipt_url_cannot_embed_credentials(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        observed=receipts(self.packet)
        observed['facebook']['planner_url']='https://secret@business.facebook.com/latest/content_calendar'
        with self.assertRaisesRegex(NativeFailure,'receipt_mismatch'):advance(self.packet,{},Driver(self.packet,[observed]),lambda *x:None,lambda s:None,lambda:self.packet,self.now)
    def test_restart_before_public_click_can_resume_completed_begin_checkpoint(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        key='begin:reviewed-fixture:'
        state={'binding':binding(self.packet),'phase':'begin_intent','checkpoints':{key:{'phase':'accepted'}}}
        driver=Driver(self.packet,[{},receipts(self.packet)]);saved=[]
        def workflow(action,*args):
            if action=='begin':state['checkpoints'][key]['phase']='success'
        def persist(s):saved.append(copy.deepcopy(s))
        self.assertEqual(advance(self.packet,state,driver,workflow,persist,lambda:copy.deepcopy(self.packet),self.now),'scheduled')
        self.assertEqual(driver.submits,1)
        self.assertEqual(driver.inspect_expectations,[False,None])
        self.assertTrue(any(s['phase']=='submission_intent' for s in saved))
    def test_resume_never_submits_without_owned_completed_begin_run(self):
        self.packet['nativeHandoff']=checkpoint(self.packet,'submitting')
        for checkpoints in [{},{'begin:reviewed-fixture:':{'phase':'accepted'}}]:
            state={'binding':binding(self.packet),'phase':'begin_intent','checkpoints':checkpoints};driver=Driver(self.packet)
            with self.assertRaises(NativeFailure):advance(self.packet,state,driver,lambda *x:None,lambda s:None,lambda:self.packet,self.now)
            self.assertEqual(driver.submits,0)
    def test_pending_reservation_only_reobserves_persisted_dispatch(self):
        state={'binding':binding(self.packet),'phase':'reserve_intent','checkpoints':{'reserve:reviewed-fixture:':{'phase':'accepted'}}};driver=Driver(self.packet);calls=[]
        self.assertEqual(advance(self.packet,state,driver,lambda *x:calls.append(x),lambda s:None,lambda:self.packet,self.now),'reserved')
        self.assertEqual(calls,[('reserve','reviewed-fixture')]);self.assertEqual(driver.submits,0)


if __name__=='__main__':unittest.main()
