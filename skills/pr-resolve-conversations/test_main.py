import json
import subprocess
import unittest
from unittest import mock

import main


def thread(tid, resolved, outdated):
    return {"id": tid, "isResolved": resolved, "isOutdated": outdated, "path": "f.py", "line": 1,
            "comments": {"nodes": [{"author": {"login": "rev"}, "body": "fix this\nmore", "url": "u"}]}}


THREADS = "\n".join(json.dumps(t) for t in [thread("done", True, False), thread("old", False, True), thread("cur", False, False)])


class Test(unittest.TestCase):
    def test_resolves_outdated_flags_current(self):
        calls = []
        with mock.patch.object(main, "gh", side_effect=lambda *a: calls.append(a) or THREADS):
            r = main.resolve_conversations(1, "o/r")
        self.assertEqual([t["id"] for t in r["resolved"]], ["old"])
        self.assertEqual([t["id"] for t in r["needs_attention"]], ["cur"])
        self.assertEqual([t["id"] for t in r["already_resolved"]], ["done"])
        self.assertIn("id=old", calls[1])
        self.assertEqual(len(calls), 2)
        self.assertFalse(r["ok"])

    def test_read_only(self):
        with mock.patch.object(main, "gh", return_value=THREADS) as gh:
            r = main.resolve_conversations(1, "o/r", auto_resolve_simple=False)
        gh.assert_called_once()
        self.assertEqual([t["id"] for t in r["unresolved"]], ["old", "cur"])
        self.assertEqual([t["id"] for t in r["needs_attention"]], ["cur"])

    def test_failed_resolve_stays_unresolved(self):
        def gh(*a):
            if "id=old" in a:
                raise subprocess.CalledProcessError(1, "gh", stderr="forbidden")
            return THREADS
        with mock.patch.object(main, "gh", side_effect=gh):
            r = main.resolve_conversations(1, "o/r")
        self.assertEqual(r["resolved"], [])
        self.assertEqual([t["id"] for t in r["unresolved"]], ["old", "cur"])


if __name__ == "__main__":
    unittest.main()
