from pathlib import Path
import unittest


class WorkflowFenceTests(unittest.TestCase):
    def test_every_production_job_has_first_step_fence(self):
        root=Path(__file__).resolve().parents[1]/'.github/workflows'
        for path in root.glob('*.yml'):
            if not path.is_file() or path.name in {'test-pipeline.yml','home-credential-transfer.yml'}:continue
            source=path.read_text(encoding='utf-8')
            with self.subTest(path=path.name):
                self.assertNotIn('\n  schedule:',source)
                self.assertNotIn('\n  push:',source)
                self.assertEqual(source.count('    steps:'),source.count('run: test "$FUNZUG_EXECUTION_OWNER" = github'))
                self.assertEqual(source.count('    steps:'),source.count('steps:\n      - name: Require GitHub execution ownership'))
                for line in source.splitlines():
                    if 'if: always()' in line:self.assertIn("vars.FUNZUG_EXECUTION_OWNER == 'github'",line)


if __name__=='__main__':unittest.main()
