import unittest
from scheduler.native_health import healthy


class NativeHealthTests(unittest.TestCase):
    def test_recent_enabled_state_is_healthy(self):
        self.assertTrue(healthy({'enabled':True,'last_checked_at':1000,'items':{}},1100))

    def test_browser_cooldown_remains_unhealthy_even_with_fresh_poll(self):
        self.assertFalse(healthy({'enabled':True,'last_checked_at':1000,'items':{},
                                 'browser_block_reason':'meta_temporarily_blocked','browser_retry_after':4600},1100))

    def test_disabled_missing_stale_and_future_states_fail(self):
        for state in [{},{'enabled':False},{'enabled':True,'last_checked_at':1,'items':{}},{'enabled':True,'last_checked_at':1200,'items':{}}]:
            self.assertFalse(healthy(state,1100))

    def test_actionable_errors_fail_without_echoing_details(self):
        self.assertFalse(healthy({'enabled':True,'last_checked_at':1000,'items':{'post':{'error':'meta_login_required'}}},1100))

    def test_historical_error_does_not_block_new_active_items(self):
        self.assertTrue(healthy({'enabled':True,'last_checked_at':1000,'active_item_ids':[], 'items':{'old':{'error':'approved_slot_too_close'}}},1100))

    def test_short_checkpoint_wait_is_healthy_but_stalled_wait_fails(self):
        state={'enabled':True,'last_checked_at':1000,'items':{'post':{'error':'checkpoint_pending_reconciliation','checkpoints':{'reserve':{'phase':'accepted','requested_at':950}}}}}
        self.assertTrue(healthy(state,1100))
        state['items']['post']['checkpoints']['reserve']['requested_at']=1
        self.assertFalse(healthy(state,1100))
