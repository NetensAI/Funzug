import base64
import copy
import io
import datetime as dt
import hashlib
import unittest
from PIL import Image
from scripts.reviewed_media import approval_fingerprint
from scheduler.native_worker import IST, NativeFailure, advance, binding, verify_delivery_package, verify_ordered_package, verify_package, verify_proof
from tests.test_native_worker import Driver, checkpoint, receipts

class NativeOrderedPackageTests(unittest.TestCase):
    def test_composer_proof_must_preserve_reviewed_order_and_format(self):
        packet=self.fixture();assets=verify_ordered_package(packet)
        proof={**binding(packet),'format':'carousel','caption':packet['caption'],'media_sha256':[hashlib.sha256(asset).hexdigest() for asset in assets],'timezone':'Asia/Kolkata','story':False,'boost':False}
        verify_proof(packet,proof,assets)
        for update in ({'media_sha256':list(reversed(proof['media_sha256']))},{'format':'reel'},{'story':True},{'boost':True},{'media_sha256':proof['media_sha256'][:1]}):
            with self.assertRaisesRegex(NativeFailure,'composer_does_not_match_approval'):
                verify_proof(packet,{**proof,**update},assets)

    def test_unimplemented_adapter_cannot_dispatch_mixed_content(self):
        packet=self.fixture();calls=[]
        with self.assertRaisesRegex(NativeFailure,'unsupported_native_media_format'):
            advance(packet,{},Driver(packet),lambda *args:calls.append(args),lambda state:None,lambda:packet,dt.datetime.now(IST))
        self.assertEqual(calls,[])

    def test_ordered_handoff_preserves_durable_submit_and_restart_invariants(self):
        class OrderedDriver(Driver):
            supported_media_formats=('carousel',)
            def proof(self,packet,assets):
                return {**binding(packet),'format':'carousel','caption':packet['caption'],'media_sha256':[hashlib.sha256(asset).hexdigest() for asset in assets],'timezone':'Asia/Kolkata','story':False,'boost':False}
            def prepared(self,packet):
                return self.proof(packet,verify_delivery_package(packet,self))
        packet=self.fixture();packet['nativeHandoff']=checkpoint(packet)
        state={'binding':binding(packet),'phase':'reserved'};saved=[];calls=[]
        driver=OrderedDriver(packet,[{},receipts(packet)])
        def workflow(action,item,receipt=None):
            calls.append(action)
            if action=='begin':packet['nativeHandoff']=checkpoint(packet,'submitting')
        def submit():
            self.assertEqual(saved[-1]['phase'],'submission_intent')
            driver.submits+=1
        driver.submit=submit
        self.assertEqual(advance(copy.deepcopy(packet),state,driver,workflow,lambda value:saved.append(copy.deepcopy(value)),lambda:copy.deepcopy(packet),dt.datetime.now(IST)),'scheduled')
        self.assertEqual(driver.submits,1)
        self.assertEqual(calls,['begin','receipt','receipt'])
        driver.observations=[receipts(packet)]
        state['phase']='submission_intent'
        advance(packet,state,driver,workflow,lambda value:None,lambda:packet,dt.datetime.now(IST))
        self.assertEqual(driver.submits,1)

    def fixture(self):
        media=[]
        for color in ('red','blue'):
            buffer=io.BytesIO();Image.new('RGB',(40,50),color).save(buffer,format='PNG')
            media.append(dict(mimeType='image/png',width=40,height=50,data=base64.b64encode(buffer.getvalue()).decode()))
        packet=dict(externalId='reviewed-carousel',format='carousel',media=media,headline='Headline',caption='Caption',claims=[{'text':'Claim'}],sources=[{'id':'primary'}],platforms=['facebook','instagram'],scheduleTimezone='Asia/Kolkata',proposedSchedule='2099-01-01T12:00:00+05:30')
        packet['contentHash']=approval_fingerprint(packet)
        return packet

    def test_verifies_original_bytes_in_exact_reviewed_order(self):
        packet=self.fixture();before=copy.deepcopy(packet)
        self.assertEqual(verify_ordered_package(packet),[base64.b64decode(a['data']) for a in packet['media']])
        self.assertEqual(packet,before)
        with self.assertRaisesRegex(NativeFailure,'unsupported_native_media_format'):
            verify_package(packet)  # Legacy live advance remains disabled for mixed formats.

    def test_changed_caption_order_bytes_platforms_and_slot_validation(self):
        for mutate in (lambda p:p.update(caption='Changed'),lambda p:p['media'].reverse(),lambda p:p.update(platforms=['facebook']),lambda p:p.update(scheduleTimezone='UTC'),lambda p:p.update(proposedSchedule='invalid')):
            packet=self.fixture();mutate(packet)
            with self.assertRaises(NativeFailure):verify_ordered_package(packet)

    def test_valid_fingerprint_cannot_make_invalid_file_safe(self):
        packet=self.fixture();packet['media'][0]['data']=base64.b64encode(b'not a decoded image').decode();packet['contentHash']=approval_fingerprint(packet)
        with self.assertRaisesRegex(NativeFailure,'invalid_reviewed_media'):verify_ordered_package(packet)
