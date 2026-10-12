# Automatic Instagram credential renewal

Facebook uses the existing non-expiring system-user credential. Instagram Login uses a separate long-lived credential refreshed weekly before its 60-day expiry. Meta documents this lifecycle in [Business Login for Instagram](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login). Dashboard-generated tokens are long-lived, as documented in [Get started](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started).

The renewal workflow stores the token, account ID, expiry, and integrity fingerprint in one encrypted environment secret, `FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL`. Updating a single bundle prevents a new token being paired with an old expiry. It checks Funzug's account identity and reads `content_publishing_limit` to verify basic and publishing access. It never creates media or publishes a post.

The private GitHub App is installed only on NetensAI/Funzug. Renewal requests an installation token with Environments write permission, which is needed to replace the encrypted environment secret. Save `FUNZUG_GH_APP_ID` and `FUNZUG_GH_APP_PRIVATE_KEY` in the `funzug-publish` environment. The private key remains a persistent credential; normal installation-token expiry is handled automatically.

One-time initialization:

1. Generate an Instagram Login token for @funzugdotcom with profile/media and publishing permissions. Disable messages, comments, and insights when the consent screen permits it.
2. Save it as `FUNZUG_INSTAGRAM_LOGIN_CANDIDATE_TOKEN` in the `funzug-publish` environment.
3. Run “Renew Instagram Login credential” with Bootstrap enabled and the actual generation time in ISO format with `+05:30`. The workflow refuses to overwrite an existing bundle and conservatively records 59 days of initial validity.
4. After the token is at least 25 hours old, run the workflow with Renew now enabled. Confirm that refresh succeeds and the encrypted bundle is updated.
5. Enable `FUNZUG_INSTAGRAM_API_MODE=instagram_login` only after the refresh test and publisher diagnostic pass. Until then, the existing Facebook Login publisher remains active.

During publishing, the Instagram Login branch requires a valid bundle and derives both account ID and token from it. Expired bundles, mismatched identities, failed integrity checks, or missing publishing access block posting. The Facebook branch keeps its existing Meta token diagnostic.

Weekly refresh, an early failure alert, and the Mini PC scheduler still need deployment verification. This document describes the implementation, not a claim that setup is complete. Meta can revoke credentials after account security events or permission removal; those events require reconnection rather than normal automatic refresh. GitHub App key revocation also requires replacing that key.
