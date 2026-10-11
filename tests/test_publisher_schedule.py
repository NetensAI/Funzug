import re
import unittest
from pathlib import Path


class PublisherScheduleTests(unittest.TestCase):
    def test_scheduled_runs_avoid_the_top_of_the_hour(self):
        workflow = Path(__file__).parents[1] / ".github" / "workflows" / "publish-approved.yml"
        text = workflow.read_text(encoding="utf-8")
        match = re.search(r'^\s+- cron: "([^"]+)"$', text, flags=re.MULTILINE)

        self.assertIsNotNone(match, "publisher workflow must keep its scheduled trigger")
        self.assertEqual(match.group(1), "2-57/5 * * * *")

        minutes = list(range(2, 58, 5))
        self.assertEqual(len(minutes), 12)
        self.assertTrue(all(minute % 5 == 2 for minute in minutes))
        self.assertNotIn(0, minutes)


if __name__ == "__main__":
    unittest.main()
