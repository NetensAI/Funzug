import base64
import json
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.brandflow_sync as sync
from PIL import Image


class BrandFlowPayloadTests(unittest.TestCase):
    def test_carousel_sync_binds_all_original_slides_in_order(self):
        with tempfile.TemporaryDirectory(dir=sync.ROOT) as directory:
            paths=[]
            for index,color in enumerate(('red','blue')):
                path=Path(directory)/f'slide-{index}.png';Image.new('RGB',(40,50),color).save(path)
                paths.append(str(path.relative_to(sync.ROOT)))
            item=dict(id='carousel-draft',format='carousel',media_paths=paths,headline='Headline',caption='Caption',scheduled_at='2099-01-01T12:00:00+05:30',platforms=['facebook','instagram'],claims=[dict(text='Claim',source_ids=['primary'],support_note='Primary evidence')],sources=[dict(id='primary',title='Source',publisher='Institute',url='https://example.org/primary',published_at=None,checked_at='2026-10-13T12:00:00+05:30')])
            packet=sync.payload_for(item);draft=packet['drafts'][0]
            self.assertEqual(packet['schemaVersion'],2)
            self.assertNotIn('image',draft)
            self.assertEqual([base64.b64decode(a['data']) for a in draft['media']],[(sync.ROOT/p).read_bytes() for p in paths])
            before=sync.approval_content_hash(item)
            item['media_paths'].reverse();self.assertNotEqual(sync.approval_content_hash(item),before)
            item['media_paths']=[paths[0],paths[0]]
            with self.assertRaisesRegex(ValueError,'Duplicate'):sync.payload_for(item)
            item['media_paths']=[str(sync.ROOT.parent/'outside.png'),paths[0]]
            with self.assertRaisesRegex(ValueError,'inside the repository'):sync.payload_for(item)
    def test_ingest_secret_trims_surrounding_whitespace(self):
        with patch.dict("os.environ", {"FUNZUG_DRAFT_INGEST_SECRET": "  " + "s" * 64 + "\r\n"}):
            self.assertEqual(sync.secret(), "s" * 64)

    def test_ingest_secret_rejects_internal_control_characters_without_echoing_them(self):
        with patch.dict("os.environ", {"FUNZUG_DRAFT_INGEST_SECRET": "s" * 32 + "\n" + "t" * 32}):
            with self.assertRaisesRegex(RuntimeError, "contains invalid characters") as raised:
                sync.secret()
            self.assertNotIn("s" * 32, str(raised.exception))

    def test_cli_entrypoint_imports_pipeline_from_scripts_directory(self):
        result = subprocess.run(
            [sys.executable, str(sync.ROOT / "scripts" / "brandflow_sync.py"), "--help"],
            cwd=sync.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("{sync,process-approvals,sync-results}", result.stdout)

    def test_payload_preserves_claim_support_and_source_metadata(self):
        with tempfile.TemporaryDirectory(dir=sync.ROOT) as directory:
            root = Path(directory)
            image = root / "post.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1080, 1350) + b"\x08\x06\x00\x00\x00")
            item = {
                "id": "funzug-example-1",
                "format": "image",
                "headline": "Example",
                "caption": "Caption",
                "media_path": str(image.relative_to(sync.ROOT)),
                "scheduled_at": "2026-11-06T22:30:00+05:30",
                "platforms": ["facebook", "instagram"],
                "claims": [{"text": "Fact", "source_ids": ["src-1"], "support_note": "The cited source states this."}],
                "sources": [{"id": "src-1", "title": "Primary source", "publisher": "Example Institute", "url": "https://example.org/report", "published_at": "2026-10-01T00:00:00Z", "checked_at": "2026-10-11T00:00:00Z"}],
            }
            payload = sync.payload_for(item)
            draft = payload["drafts"][0]
            self.assertEqual(payload["brandSlug"], "funzug")
            self.assertEqual(draft["scheduleTimezone"], "Asia/Kolkata")
            self.assertEqual(draft["proposedSchedule"], "2026-11-06T22:30:00+05:30")
            self.assertEqual(draft["claims"][0]["support_note"], "The cited source states this.")
            self.assertEqual(draft["sources"][0]["publisher"], "Example Institute")
            self.assertEqual(base64.b64decode(draft["image"]["data"]), image.read_bytes())

    def test_payload_rejects_non_image_or_external_asset_path(self):
        item = {"id": "bad", "format": "carousel", "media_path": "outside.png"}
        with self.assertRaisesRegex(ValueError, "2 to 10"):
            sync.payload_for(item)

    def test_approval_uses_brandflow_selected_ist_schedule(self):
        item = {"id": "funzug-example-1", "status": "draft", "scheduled_at": "2026-11-06T22:30:00+05:30"}
        drafts = {"items": [item]}
        queue = {"items": []}
        status = {
            "status": "approved",
            "publicationAuthorized": True,
            "reviewChecks": {},
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2026-11-12T19:15:00+05:30",
            "reviewedBy": "vatsal",
            "reviewNote": "Approved for scheduled publishing at Nov 12, 2026, 7:15 PM IST",
            "reviewedAt": "2026-11-12T12:00:00Z",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={item["id"]: status}),
            patch.object(sync.pipeline, "load_json", side_effect=[drafts, queue, queue]),
            patch.object(sync, "require_matching_approved_content") as match,
            patch.object(sync.pipeline, "host_and_approve_draft") as process,
        ):
            sync.process_approvals()
        passed_drafts = process.call_args.args[0]
        self.assertEqual(passed_drafts["items"][0]["scheduled_at"], "2026-11-12T19:15:00+05:30")
        self.assertEqual(process.call_args.args[5], {"approvalConfirmed": True})
        match.assert_called_once_with(item, status)

    def test_expired_approval_is_skipped_without_blocking_future_approval(self):
        expired = {"id": "funzug-example-past", "status": "draft", "scheduled_at": "2026-11-06T22:30:00+05:30"}
        future = {"id": "funzug-example-future", "status": "draft", "scheduled_at": "2026-11-06T22:30:00+05:30"}
        drafts = {"items": [expired, future]}
        queue = {"items": []}
        expired_status = {
            "status": "approved",
            "publicationAuthorized": True,
            "reviewChecks": {"approvalConfirmed": True},
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2000-01-01T19:15:00+05:30",
            "reviewedBy": "vatsal",
            "reviewNote": "Approved for scheduled publishing",
            "reviewedAt": "2000-01-01T12:00:00Z",
        }
        future_status = {
            **expired_status,
            "proposedSchedule": "2999-01-01T19:15:00+05:30",
            "reviewedAt": "2998-12-31T12:00:00Z",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={
                expired["id"]: expired_status,
                future["id"]: future_status,
            }),
            patch.object(sync.pipeline, "load_json", side_effect=[drafts, queue, queue]),
            patch.object(sync, "require_matching_approved_content") as match,
            patch.object(sync.pipeline, "host_and_approve_draft") as process,
        ):
            self.assertEqual(sync.process_approvals(), 0)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.args[2], future["id"])
        match.assert_called_once_with(future, future_status)

    def test_native_approval_is_staged_with_api_delivery_disabled(self):
        item={'id':'native-fixture','status':'draft'}
        status={'status':'approved','publicationAuthorized':True,
                'contentHash':'a'*64,
                'scheduleTimezone':'Asia/Kolkata','proposedSchedule':'2999-01-01T19:15:00+05:30',
                'reviewedBy':'vatsal','reviewNote':'Approved','reviewChecks':{'approvalConfirmed':True}}
        with (
            patch.dict('os.environ',{'FUNZUG_DELIVERY_MODE':'meta_native'}),
            patch.object(sync,'secret',return_value='s'*64),
            patch.object(sync,'api_url',return_value='https://example.test/api'),
            patch.object(sync,'api_status',return_value={item['id']:status}),
            patch.object(sync.pipeline,'load_json',side_effect=[{'items':[item]},{'items':[]},{'items':[]}]),
            patch.object(sync,'require_matching_approved_content'),
            patch.object(sync,'approve_native_draft') as process,
            patch.object(sync.pipeline,'host_and_approve_draft') as public_upload,
        ):
            sync.process_approvals()
        staged=process.call_args.args[0]['items'][0]
        self.assertEqual(staged['delivery_mode'],'meta_native_pending')
        self.assertFalse(sync.pipeline.workflow_delivery_allowed(staged))
        public_upload.assert_not_called()

    def test_private_native_staging_keeps_reviewed_hash_and_never_uploads(self):
        candidate={'id':'native-fixture','status':'draft','format':'carousel'}
        with patch.object(sync,'approval_content_hash',return_value='a'*64),patch.object(sync.pipeline,'validate_draft_queue',return_value=[]),patch.object(sync.pipeline,'approve') as approve:
            sync.approve_native_draft({'items':[candidate]},{'items':[]},candidate['id'],'vatsal','Approved','2026-10-14T11:00:00+05:30','a'*64)
        staged=approve.call_args.args[0]['items'][0]
        self.assertEqual(staged['reviewed_content_hash'],'a'*64)
        self.assertEqual(staged['delivery_mode'],'meta_native_pending')
        self.assertFalse(sync.pipeline.workflow_delivery_allowed(staged))
        self.assertNotIn('delivery_mode',candidate)
        with patch.object(sync,'approval_content_hash',return_value='b'*64),patch.object(sync.pipeline,'approve') as approve:
            with self.assertRaisesRegex(RuntimeError,'Reviewed native media changed'):
                sync.approve_native_draft({'items':[candidate]},{'items':[]},candidate['id'],'vatsal','Approved',None,'a'*64)
        approve.assert_not_called()

    def test_published_item_does_not_block_later_approvals(self):
        published = {"id": "already-posted", "status": "published"}
        queue = {"items": [published]}
        status = {
            "status": "approved", "publicationAuthorized": True,
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2999-01-01T19:15:00+05:30",
            "reviewedBy": "vatsal", "reviewNote": "Original approval",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={published["id"]: status}),
            patch.object(sync.pipeline, "load_json", side_effect=[{"items": []}, queue]),
            patch.object(sync.pipeline, "host_and_approve_draft") as upload,
        ):
            self.assertEqual(sync.process_approvals(), 0)
        upload.assert_not_called()

    def test_sync_results_sends_only_fully_published_posts(self):
        completed = {
            "id": "published-example", "status": "published",
            "platforms": ["facebook"],
            "platform_results": {
                "facebook": {"status": "published", "post_id": "page_post", "published_at": "2026-10-11T17:00:00Z"},
                "instagram": {"status": "published", "post_id": "ig_post", "published_at": "2026-10-11T16:00:00Z"},
            },
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api/integrations/funzug/drafts"),
            patch.object(sync.pipeline, "load_json", side_effect=[{"items": [{"id": completed["id"], "platforms": ["facebook", "instagram"]}]}, {"items": [completed, {"id": "other", "status": "approved"}]}]),
            patch.object(sync, "api_request", return_value={}) as request,
        ):
            self.assertEqual(sync.sync_results(), 0)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "PUT")
        self.assertEqual(request.call_args.args[1], "https://example.test/api/integrations/funzug/drafts")
        payload = request.call_args.args[3]
        self.assertEqual(payload["externalId"], completed["id"])
        self.assertEqual(set(payload["platformResults"]), {"facebook", "instagram"})

    def test_failed_result_sync_omits_error_details(self):
        failed={"id":"partial","status":"failed","platform_results":{"facebook":{"status":"failed","failed_at":"2026-10-11T17:00:00Z","error":"private-details"},"instagram":{"status":"published","post_id":"ig-post","published_at":"2026-10-11T16:00:00Z"}}}
        with patch.object(sync,"secret",return_value="s"*64),patch.object(sync,"api_url",return_value="https://example.test/api/integrations/funzug/drafts"),patch.object(sync.pipeline,"load_json",side_effect=[{"items":[{"id":"partial","platforms":["facebook","instagram"]}]},{"items":[failed]}]),patch.object(sync,"api_request",return_value={}) as request:
            self.assertEqual(sync.sync_results(),0)
        results=request.call_args.args[3]["platformResults"]
        self.assertEqual(results["facebook"],{"status":"failed","failedAt":"2026-10-11T17:00:00Z"})
        self.assertEqual(results["instagram"]["postId"],"ig-post")

    def test_api_request_identifies_funzug_workflow(self):
        with patch.object(sync.urllib.request,"urlopen") as network:
            network.return_value.__enter__.return_value.read.return_value=b'{}'
            sync.api_request("PUT","https://example.test/api/integrations/funzug/drafts","s"*64,{})
        self.assertEqual(network.call_args.args[0].get_header("User-agent"),"FunzugWorkflow/1.0")


if __name__ == "__main__":
    unittest.main()
