import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('queue_extension', Path(__file__).resolve().parents[1] / 'home-server/monitor_queue_extension.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_allowlisted_output_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'queue.json'
            path.write_text(json.dumps({'items': [{'id': 'funzug-test-topic', 'status': 'approved', 'caption': 'PRIVATE', 'access_token': 'PRIVATE', 'topic_keys': ['test-topic', 'PRIVATE SECRET']}]}))
            result = module.summarize(path)
            self.assertTrue(result['available'])
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertEqual(result['count'], 1)

    def test_invalid_identifier_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'queue.json'
            path.write_text('{"items":[{"id":"invalid"}]}')
            self.assertFalse(module.summarize(path)['available'])

    def test_install_preserves_monitor_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / '.local/lib/funzug-monitor'
            base.mkdir(parents=True)
            target = base / 'monitor_health.py'
            source = '"""Monitor."""\nfrom __future__ import annotations\ndef main():\n    try:\n        print(json.dumps(collect(), indent=2))\n    except Exception: pass\n'
            target.write_text(source)
            with patch.object(module.Path, 'home', return_value=Path(folder)):
                module.install()
                module.install()
            self.assertEqual((base / 'monitor_health_before_queue.py').read_text(), source)
            compile(target.read_text(), str(target), 'exec')


if __name__ == '__main__':
    unittest.main()
