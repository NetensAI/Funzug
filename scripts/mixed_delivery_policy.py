"""Shared fail-closed mixed delivery scope; acceptance never enables news items."""
ACCEPTANCE_IDS = frozenset({'funzug-test-2026-10-16-carousel','funzug-test-2026-10-16-reel'})


def mixed_delivery_enabled(identifier, environment):
    return environment.get('FUNZUG_NATIVE_MIXED_ENABLED') == '1' or (
        environment.get('FUNZUG_NATIVE_ACCEPTANCE_ENABLED') == '1'
        and isinstance(identifier, str) and identifier in ACCEPTANCE_IDS
    )
