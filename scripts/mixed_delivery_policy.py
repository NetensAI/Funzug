"""Shared fail-closed mixed delivery scope; acceptance never enables news items."""
ACCEPTANCE_IDS = frozenset({'funzug-test-2026-10-16-carousel'})
CANCELLED_IDS = frozenset({'funzug-test-2026-10-16-reel'})


def mixed_delivery_enabled(identifier, environment):
    if isinstance(identifier, str) and identifier in CANCELLED_IDS:
        return False
    return environment.get('FUNZUG_NATIVE_MIXED_ENABLED') == '1' or (
        environment.get('FUNZUG_NATIVE_ACCEPTANCE_ENABLED') == '1'
        and isinstance(identifier, str) and identifier in ACCEPTANCE_IDS
    )
