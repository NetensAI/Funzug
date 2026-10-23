import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from home_server import checkpoints


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.queue=Path(self.temp.name)/'queue.json';self.queue.write_text('{"items":[]}')
        self.packet={'externalId':'fixture','proposedSchedule':'2099-10-25T12:25:00+05:30',
                     'contentHash':'a'*64,'platforms':['facebook','instagram'],
                     'caption':'fixture','headline':'fixture','nativeHandoff':None}
        self.state={}
        self.patches=[patch.object(checkpoints,'QUEUE',self.queue),
                      patch.object(checkpoints,'require_home'),
                      patch.object(checkpoints,'read_api',side_effect=lambda *a:copy.deepcopy(self.packet)),
                      patch.object(checkpoints,'api_request',side_effect=self.api)]
        for item in self.patches:item.start();self.addCleanup(item.stop)
        self.dispatch=checkpoints.LocalDispatcher({'draft_secret':'fixture'},self.state,lambda _:None)

    def api(self,method,url,secret,payload):
        self.packet['nativeHandoff']=copy.deepcopy(payload['handoff'])
        return {'externalId':'fixture','state':payload['handoff']['state']}

    def test_reservation_and_begin_are_local_and_durable(self):
        self.dispatch('reserve','fixture');self.dispatch('begin','fixture')
        row=json.loads(self.queue.read_text())['items'][0]
        self.assertEqual(row['native_handoff']['state'],'submitting')
        self.assertEqual(self.state['checkpoints']['begin:fixture:']['backend'],'home')

    def test_failed_handoff_reuses_same_reservation(self):
        with patch.object(checkpoints,'api_request',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.dispatch('reserve','fixture')
        before=json.loads(self.queue.read_text())['items'][0]['native_handoff']['reserved_at']
        self.dispatch('reserve','fixture')
        self.assertEqual(before,self.packet['nativeHandoff']['reserved_at'])

    def test_owner_fence_blocks_before_any_write(self):
        with patch.object(checkpoints,'require_home',side_effect=RuntimeError('not owner')):
            with self.assertRaises(RuntimeError):self.dispatch('reserve','fixture')
        self.assertEqual(json.loads(self.queue.read_text()),{'items':[]})

    def test_changed_content_refused(self):
        self.dispatch('reserve','fixture');self.packet['contentHash']='b'*64
        with self.assertRaises(checkpoints.NativeFailure):self.dispatch('begin','fixture')

    def test_no_workflow_dispatch_implementation(self):
        source=Path(checkpoints.__file__).read_text()
        self.assertNotIn('/dispatches',source)
        self.assertNotIn('workflow_dispatch',source)

    def test_pipeline_future_slot_preserved(self):
        self.dispatch('reserve','fixture')
        row=json.loads(self.queue.read_text())['items'][0]
        self.assertEqual(row['scheduled_at'],self.packet['proposedSchedule'])
        self.assertEqual(row['platforms'],self.packet['platforms'])


if __name__=='__main__':unittest.main()
