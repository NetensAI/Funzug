import unittest
from pathlib import Path


class MediaValidatorWorkflowTests(unittest.TestCase):
    def test_queue_writers_checkout_current_main_after_serialization(self):
        root = Path(__file__).resolve().parents[1]
        for filename in ['native-meta-handoff.yml', 'brandflow-draft-approval.yml',
                         'approve-scheduled-post.yml', 'publish-approved.yml']:
            content = (root / '.github/workflows' / filename).read_text()
            self.assertIn('group: funzug-queue-writes', content)
            for block in content.split('uses: actions/checkout@')[1:]:
                with self.subTest(workflow=filename):
                    self.assertIn('ref: main', block.split('- name:', 1)[0])

    def test_affected_jobs_install_validator_before_use(self):
        root = Path(__file__).resolve().parents[1]
        cases = {
            'native-meta-handoff.yml': ['Stage existing owner approval before native reservation'],
            'brandflow-draft-approval.yml': ['Validate drafts and publishing queue'],
            'approve-scheduled-post.yml': ['Validate the draft inbox and publishing queue'],
            'refresh-pending-drafts.yml': ['Validate private review-only drafts'],
            'publish-approved.yml': ['Validate queue', 'Publish due, approved posts'],
        }
        for filename, steps in cases.items():
            content = (root / '.github/workflows' / filename).read_text()
            for step in steps:
                with self.subTest(workflow=filename, step=step):
                    position = content.index('- name: ' + step)
                    previous_job = content.rfind('    steps:', 0, position)
                    self.assertIn('uses: ./.github/actions/setup-media-validator',
                                  content[previous_job:position])

    def test_action_uses_pinned_dependency_and_decoder_checks(self):
        root = Path(__file__).resolve().parents[1]
        content = (root / '.github/actions/setup-media-validator/action.yml').read_text()
        self.assertIn('-r media-host/requirements.txt', content)
        self.assertIn('from PIL import Image', content)
        self.assertIn('ffmpeg -version', content)
        self.assertIn('ffprobe -version', content)


if __name__ == '__main__':
    unittest.main()
