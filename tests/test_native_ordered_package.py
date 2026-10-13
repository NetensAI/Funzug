import base64
import copy
import io
import unittest
from PIL import Image
from scripts.reviewed_media import approval_fingerprint
from scheduler.native_worker import NativeFailure, verify_ordered_package, verify_package

class NativeOrderedPackageTests(unittest.TestCase):
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
