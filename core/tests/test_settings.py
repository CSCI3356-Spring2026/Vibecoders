import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase


class TestSettingsTests(SimpleTestCase):
    def test_test_suite_uses_fast_password_hasher(self):
        self.assertEqual(settings.PASSWORD_HASHERS, ["django.contrib.auth.hashers.MD5PasswordHasher"])

    def test_settings_fall_back_to_sqlite_when_database_url_package_is_missing(self):
        result = self._run_settings_import_with_blocked_dj_database_url(
            "import vibecoders.settings as settings; print(settings.DATABASES['default']['ENGINE'])"
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("django.db.backends.sqlite3", result.stdout)

    def test_settings_require_dj_database_url_when_database_url_is_set(self):
        result = self._run_settings_import_with_blocked_dj_database_url(
            "import vibecoders.settings",
            database_url="postgres://user:pass@localhost:5432/padly",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Install dj-database-url to use DATABASE_URL.", result.stderr)

    def test_ci_workflow_keeps_existing_quality_gates_and_deploy_check(self):
        repo_root = Path(__file__).resolve().parents[2]
        workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("- run: ruff check .", workflow)
        self.assertIn("- run: ruff format --check .", workflow)
        self.assertIn("- run: python manage.py check", workflow)
        self.assertIn("- run: python manage.py makemigrations --check --dry-run", workflow)
        self.assertIn("- run: python manage.py test", workflow)
        self.assertIn("python manage.py check --deploy", workflow)
        self.assertIn('DJANGO_DEBUG: "false"', workflow)
        self.assertIn("DJANGO_SECRET_KEY:", workflow)
        self.assertIn("DJANGO_ALLOWED_HOSTS:", workflow)
        self.assertIn("DJANGO_CSRF_TRUSTED_ORIGINS:", workflow)
        self.assertIn("DATABASE_URL:", workflow)
        self.assertIn("CHANNEL_REDIS_URL:", workflow)
        self.assertIn("CACHE_REDIS_URL:", workflow)

    def _run_settings_import_with_blocked_dj_database_url(self, command, *, database_url=""):
        repo_root = Path(__file__).resolve().parents[2]
        import_blocker = "\n".join(
            [
                "import builtins",
                "_real_import = builtins.__import__",
                "def _blocked(name, globals=None, locals=None, fromlist=(), level=0):",
                "    if name == 'dj_database_url':",
                "        raise ImportError('blocked for test')",
                "    return _real_import(name, globals, locals, fromlist, level)",
                "builtins.__import__ = _blocked",
            ]
        )

        with TemporaryDirectory() as temp_dir:
            sitecustomize_path = Path(temp_dir) / "sitecustomize.py"
            sitecustomize_path.write_text(import_blocker, encoding="utf-8")

            env = os.environ.copy()
            env["DJANGO_DEBUG"] = "true"
            env["PYTHONPATH"] = os.pathsep.join([temp_dir, str(repo_root)])
            if database_url:
                env["DATABASE_URL"] = database_url
            else:
                env.pop("DATABASE_URL", None)

            return subprocess.run(
                [sys.executable, "-c", command],
                capture_output=True,
                check=False,
                cwd=repo_root,
                env=env,
                text=True,
            )
