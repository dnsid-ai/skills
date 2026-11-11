import json
import subprocess
import unittest
from unittest import mock

import main


class ParseLinks(unittest.TestCase):
    def test_keywords_and_cross_repo(self):
        body = "Closes #1, fixes: #2\nRefs other/repo#3\nresolved #1\nsee #9\nprefix#4"
        self.assertEqual(main.parse_links(body, "o/r"), [("o/r", 1), ("o/r", 2), ("other/repo", 3)])

    def test_empty(self):
        self.assertEqual(main.parse_links(None, "o/r"), [])


def fake_gh(issues, calls):
    def gh(*args):
        calls.append(args)
        path = args[-1] if args[1] != "-X" else args[3]
        if path == "repos/o/r/pulls/5":
            return json.dumps({"body": "Fixes #1\nRefs x/y#2", "base": {"repo": {"full_name": "o/r"}}})
        if path in issues:
            return json.dumps(issues[path])
        if path.endswith("/labels"):
            return "[]"
        raise subprocess.CalledProcessError(1, "gh", stderr="404")
    return gh


class Verify(unittest.TestCase):
    def test_valid_and_labels(self):
        calls = []
        issues = {"repos/o/r/issues/1": {"state": "open"}, "repos/x/y/issues/2": {"state": "open"}}
        with mock.patch.object(main, "gh", side_effect=fake_gh(issues, calls)):
            r = main.verify_issue_linked(5, "o/r", "in-progress")
        self.assertTrue(r["ok"])
        self.assertEqual(r["linked_issues"], ["o/r#1", "x/y#2"])
        self.assertEqual(r["labeled"], ["o/r#1", "x/y#2"])

    def test_closed_missing_and_pr_block_labeling(self):
        calls = []
        issues = {"repos/o/r/issues/1": {"state": "closed"}}
        with mock.patch.object(main, "gh", side_effect=fake_gh(issues, calls)):
            r = main.verify_issue_linked(5, "o/r", "in-progress")
        self.assertFalse(r["ok"])
        self.assertEqual(r["errors"], ["o/r#1 is closed", "x/y#2 does not exist or is not accessible"])
        self.assertEqual(r["labeled"], [])
        self.assertFalse(any("-X" in c for c in calls))

    def test_pull_request_is_not_an_issue(self):
        issues = {"repos/o/r/issues/1": {"state": "open", "pull_request": {}}, "repos/x/y/issues/2": {"state": "open"}}
        with mock.patch.object(main, "gh", side_effect=fake_gh(issues, [])):
            r = main.verify_issue_linked(5, "o/r")
        self.assertEqual(r["errors"], ["o/r#1 is a pull request, not an issue"])


if __name__ == "__main__":
    unittest.main()
