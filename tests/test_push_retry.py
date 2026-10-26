"""scripts/push_retry.sh must win a race against a push that lands first: python3 -m unittest discover tests"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "push_retry.sh"
IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}  # CI runners have no git identity; rebasing needs one


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env={**os.environ, **IDENT}).stdout


class PushRetry(unittest.TestCase):
    def test_push_succeeds_when_remote_moved_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            git(tmp, "init", "-q", "--bare", "-b", "main", "origin.git")
            for name in ("a", "b"):
                git(tmp, "clone", "-q", "origin.git", name)
            (tmp / "a" / "one.txt").write_text("1")
            git(tmp / "a", "add", "."); git(tmp / "a", "commit", "-qm", "one"); git(tmp / "a", "push", "-q", "origin", "HEAD:main")
            git(tmp / "b", "pull", "-q", "origin", "main")
            (tmp / "a" / "two.txt").write_text("2")  # a pushes first ...
            git(tmp / "a", "add", "."); git(tmp / "a", "commit", "-qm", "two"); git(tmp / "a", "push", "-q", "origin", "HEAD:main")
            (tmp / "b" / "three.txt").write_text("3")  # ... so b's push is now behind
            git(tmp / "b", "add", "."); git(tmp / "b", "commit", "-qm", "three")
            res = subprocess.run(["bash", str(SCRIPT)], cwd=tmp / "b", capture_output=True, text=True, env={**os.environ, **IDENT})
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(sorted(git(tmp, "--git-dir=origin.git", "ls-tree", "--name-only", "main").split()), ["one.txt", "three.txt", "two.txt"])


if __name__ == "__main__":
    unittest.main()
