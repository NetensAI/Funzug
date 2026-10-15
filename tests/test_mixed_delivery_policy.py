import unittest
from scripts.mixed_delivery_policy import ACCEPTANCE_IDS, mixed_delivery_enabled


class MixedDeliveryPolicyTests(unittest.TestCase):
    def test_acceptance_is_exactly_scoped_and_default_off(self):
        for identifier in ACCEPTANCE_IDS:
            self.assertFalse(mixed_delivery_enabled(identifier,{}))
            self.assertTrue(mixed_delivery_enabled(identifier,{'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1'}))
        for identifier in ('news-carousel','funzug-test-2026-10-16-reel','funzug-test-2026-10-16-reel-extra',None,{}):
            self.assertFalse(mixed_delivery_enabled(identifier,{'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1'}))

    def test_cancelled_test_reel_stays_blocked_under_every_enable_flag(self):
        reel = 'funzug-test-2026-10-16-reel'
        for environment in ({}, {'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1'}, {'FUNZUG_NATIVE_MIXED_ENABLED':'1'}, {'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1','FUNZUG_NATIVE_MIXED_ENABLED':'1'}):
            self.assertFalse(mixed_delivery_enabled(reel, environment))
