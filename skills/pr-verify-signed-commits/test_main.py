import json
import unittest
from unittest import mock

import main


def commit(sha, verified, reason="valid"):
    return {"sha": sha, "author": {"login": "octocat"},
            "commit": {"message": f"msg {sha}\n\nbody", "author": {"email": "o@example.com"},
                       "verification": {"verified": verified, "reason": reason}}}


class Test(unittest.TestCase):
    def test_reports_only_unverified(self):
        out = "\n".join(json.dumps(c) for c in [commit("a", True), commit("b", False, "unsigned")])
        with mock.patch.object(main, "gh", return_value=out):
            r = main.verify_signed_commits(1, "o/r")
        self.assertFalse(r["ok"])
        self.assertEqual(r["total_commits"], 2)
        self.assertEqual(r["unsigned_commits"], [{"sha": "b", "reason": "unsigned", "subject": "msg b", "author": "octocat"}])
        self.assertTrue(r["remediation"])

    def test_all_signed(self):
        with mock.patch.object(main, "gh", return_value=json.dumps(commit("a", True))):
            r = main.verify_signed_commits(1, "o/r")
        self.assertTrue(r["ok"])
        self.assertEqual(r["remediation"], [])


if __name__ == "__main__":
    unittest.main()
