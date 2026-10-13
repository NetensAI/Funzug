import unittest
from unittest.mock import Mock, patch

from scheduler.native_dispatch import CheckpointDispatcher
from scheduler.native_worker import NativeFailure


class DispatchTests(unittest.TestCase):
    def test_only_completed_matching_bot_run_confirms_checkpoint(self):
        state={'checkpoints':{'begin:item:':{'correlation':'abc','phase':'accepted'}}}
        rows=[{'id':9,'display_title':'Native Meta begin item abc','actor':{'login':'funzug-automation-netensai[bot]'},'status':'completed','conclusion':'success'}]
        save=Mock()
        with patch('scheduler.native_dispatch.github',return_value={'workflow_runs':rows}),patch('scheduler.native_dispatch.build_opener') as send:
            CheckpointDispatcher('not-a-real-token',state,save)('begin','item')
        send.assert_not_called()
        self.assertEqual(state['checkpoints']['begin:item:']['phase'],'success')
        self.assertEqual(state['checkpoints']['begin:item:']['run_id'],9)

    def test_unrelated_success_does_not_confirm_or_redispatch(self):
        state={'checkpoints':{'reserve:item:':{'correlation':'abc','phase':'dispatch_intent'}}}
        rows=[{'id':9,'display_title':'Native Meta reserve other abc','actor':{'login':'funzug-automation-netensai[bot]'},'status':'completed','conclusion':'success'}]
        with patch('scheduler.native_dispatch.github',return_value={'workflow_runs':rows}),patch('scheduler.native_dispatch.build_opener') as send,patch('scheduler.native_dispatch.time.monotonic',side_effect=[0,1,100]),patch('scheduler.native_dispatch.time.sleep'):
            with self.assertRaisesRegex(NativeFailure,'pending_reconciliation'):CheckpointDispatcher('fake',state,Mock())('reserve','item')
        send.assert_not_called()
        self.assertEqual(state['checkpoints']['reserve:item:']['phase'],'dispatch_intent')

    def test_failed_correlated_run_stops_before_browser_submission(self):
        state={'checkpoints':{'begin:item:':{'correlation':'abc','phase':'accepted'}}}
        rows=[{'id':9,'display_title':'Native Meta begin item abc','actor':{'login':'funzug-automation-netensai[bot]'},'status':'completed','conclusion':'failure'}]
        with patch('scheduler.native_dispatch.github',return_value={'workflow_runs':rows}),patch('scheduler.native_dispatch.build_opener') as send:
            with self.assertRaisesRegex(NativeFailure,'workflow_failed'):CheckpointDispatcher('fake',state,Mock())('begin','item')
        send.assert_not_called()
        self.assertEqual(state['checkpoints']['begin:item:']['phase'],'failed')

    def test_dispatch_intent_is_saved_before_transmission_and_timeout_is_not_replayed(self):
        state={};seen=[]
        def persist(value):seen.append(value['checkpoints']['reserve:item:']['phase'])
        opener=Mock()
        def fail(*args,**kwargs):
            self.assertEqual(seen,['dispatch_intent'])
            raise TimeoutError()
        opener.open.side_effect=fail
        with patch('scheduler.native_dispatch.build_opener',return_value=opener):
            with self.assertRaisesRegex(NativeFailure,'dispatch_unconfirmed'):CheckpointDispatcher('fake',state,persist)('reserve','item')
        with patch('scheduler.native_dispatch.github',return_value={'workflow_runs':[]}),patch('scheduler.native_dispatch.build_opener') as send,patch('scheduler.native_dispatch.time.monotonic',side_effect=[0,100]):
            with self.assertRaisesRegex(NativeFailure,'pending_reconciliation'):CheckpointDispatcher('fake',state,persist)('reserve','item')
        send.assert_not_called()

    def test_dispatcher_rejects_publication_or_arbitrary_workflow_actions(self):
        for action in ['published','publish','approve','dashboard']:
            with self.assertRaisesRegex(NativeFailure,'unsupported'):CheckpointDispatcher('fake',{},Mock())(action,'item')


if __name__=='__main__':unittest.main()
