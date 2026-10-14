import unittest
from scripts.mixed_delivery_policy import ACCEPTANCE_IDS, mixed_delivery_enabled


class MixedDeliveryPolicyTests(unittest.TestCase):
    def test_acceptance_is_exactly_scoped_and_default_off(self):
        for identifier in ACCEPTANCE_IDS:
            self.assertFalse(mixed_delivery_enabled(identifier,{}))
            self.assertTrue(mixed_delivery_enabled(identifier,{'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1'}))
        for identifier in ('news-carousel','funzug-test-2026-10-16-reel-extra',None,{}):
            self.assertFalse(mixed_delivery_enabled(identifier,{'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1'}))
