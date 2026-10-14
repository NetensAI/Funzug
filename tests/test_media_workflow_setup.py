from pathlib import Path
import unittest


class MediaWorkflowSetupTests(unittest.TestCase):
    def test_dashboard_docker_context_excludes_private_backups(self):
        root=Path(__file__).resolve().parents[1]
        rules=(root/'brandflow/.dockerignore').read_text().splitlines()
        self.assertIn('.env',rules)
        self.assertIn('.backups',rules)

    def test_delivery_and_review_workflows_install_media_runtime(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('native-meta-handoff','brandflow-draft-approval','approve-scheduled-post','refresh-pending-drafts','publish-approved'):
            source=(root/'.github/workflows'/f'{name}.yml').read_text()
            self.assertIn('uses: ./.github/actions/setup-media-validator',source,name)
        publisher=(root/'.github/workflows/publish-approved.yml').read_text()
        self.assertEqual(publisher.count('uses: ./.github/actions/setup-media-validator'),2)
        native=(root/'.github/workflows/native-meta-handoff.yml').read_text()
        self.assertIn("vars.FUNZUG_NATIVE_ACCEPTANCE_ENABLED || '0'",native)
