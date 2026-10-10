# Draft inbox

Daily Codex runs save 7 to 10 review-only items here, with generated images under `drafts/assets/`. Each draft includes its caption, proposed US Eastern publishing time, source records, claim-to-source IDs, and a `support_note` for every factual claim. Images must be verified at exactly 1080x1350.

Drafts do not need a public media URL and are never read by the publishing workflow. Check them with:

```text
python funzug_pipeline.py validate-drafts
```

After a human reviews a draft and makes its image available at a public HTTPS URL, stage it into the separate publishing queue:

```text
python funzug_pipeline.py stage-draft --id ITEM_ID --public-media-url https://media.example.com/image.png
```

Staging only copies the item into `queue.json` as an unapproved draft. A human must still explicitly approve it with a named reviewer and review note before the due-time publisher can post. Never add an approval record on the owner's behalf.

Source URL metadata and support notes are research evidence for review, not proof that claims are true. Researchers must inspect sources, and the owner must review claims, caption, image, platforms, and schedule.
