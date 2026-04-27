import json
import os
import platform
import subprocess
import sys
import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase

HAS_DJ_DATABASE_URL = find_spec("dj_database_url") is not None
PYTHON_SUBPROCESS_PREFIX = ["/usr/bin/arch", f"-{platform.machine()}"] if sys.platform == "darwin" else []


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

    def test_settings_disable_raw_admin_backend_when_admin_is_disabled(self):
        result = self._run_python_subprocess(
            "import json; import vibecoders.settings as settings; print(json.dumps(settings.AUTHENTICATION_BACKENDS))",
            extra_env={"DJANGO_ADMIN_ENABLED": "false"},
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        backends = json.loads(result.stdout)
        self.assertNotIn("django.contrib.auth.backends.ModelBackend", backends)
        self.assertIn("allauth.account.auth_backends.AuthenticationBackend", backends)

    def test_seed_demo_data_is_treated_as_local_debug_command(self):
        result = self._run_python_subprocess(
            "import sys; sys.argv = ['manage.py', 'seed_demo_data']; "
            "import vibecoders.settings as settings; "
            "print(settings.DEBUG)",
            extra_env={"DJANGO_DEBUG": None},
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "True")

    def test_root_urls_mount_admin_only_when_enabled(self):
        urlpatterns_command = "".join(
            [
                "import json; import django; django.setup(); ",
                "import vibecoders.urls as urls; ",
                "print(json.dumps([",
                "getattr(pattern.pattern, '_route', str(pattern.pattern)) ",
                "for pattern in urls.urlpatterns",
                "]))",
            ]
        )
        disabled_result = self._run_python_subprocess(
            urlpatterns_command,
            extra_env={"DJANGO_ADMIN_ENABLED": "false"},
        )
        enabled_result = self._run_python_subprocess(
            urlpatterns_command,
            extra_env={"DJANGO_ADMIN_ENABLED": "true"},
        )

        self.assertEqual(disabled_result.returncode, 0, msg=disabled_result.stderr)
        self.assertEqual(enabled_result.returncode, 0, msg=enabled_result.stderr)
        self.assertNotIn("admin/", json.loads(disabled_result.stdout))
        self.assertIn("admin/", json.loads(enabled_result.stdout))

    @unittest.skipUnless(HAS_DJ_DATABASE_URL, "dj-database-url is required for production DATABASE_URL settings tests.")
    def test_production_settings_enable_whitenoise_manifest_storage(self):
        result = self._run_python_subprocess(
            (
                "import json; import vibecoders.settings as settings; "
                "print(json.dumps({'middleware': settings.MIDDLEWARE[:2], "
                "'staticfiles_backend': settings.STORAGES['staticfiles']['BACKEND']}))"
            ),
            extra_env={
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "test-secret",
                "DJANGO_ALLOWED_HOSTS": "padly.example.com",
                "DATABASE_URL": "postgresql://user:pass@localhost:5432/padly",
                "CHANNEL_REDIS_URL": "redis://localhost:6379/0",
                "CACHE_REDIS_URL": "redis://localhost:6379/1",
            },
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["middleware"][0], "django.middleware.security.SecurityMiddleware")
        self.assertEqual(payload["middleware"][1], "whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertEqual(
            payload["staticfiles_backend"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    @unittest.skipUnless(HAS_DJ_DATABASE_URL, "dj-database-url is required for production DATABASE_URL settings tests.")
    def test_render_defaults_cover_allowed_hosts_and_csrf_when_explicit_values_are_missing(self):
        result = self._run_python_subprocess(
            (
                "import json; import vibecoders.settings as settings; "
                "print(json.dumps({'allowed_hosts': settings.ALLOWED_HOSTS, "
                "'csrf_origins': settings.CSRF_TRUSTED_ORIGINS}))"
            ),
            extra_env={
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "test-secret",
                "DJANGO_ALLOWED_HOSTS": "",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "",
                "RENDER_EXTERNAL_HOSTNAME": "padly.onrender.com",
                "RENDER_EXTERNAL_URL": "https://padly.onrender.com",
                "DATABASE_URL": "postgresql://user:pass@localhost:5432/padly",
                "CHANNEL_REDIS_URL": "redis://localhost:6379/0",
                "CACHE_REDIS_URL": "redis://localhost:6379/1",
            },
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["allowed_hosts"], ["padly.onrender.com"])
        self.assertEqual(payload["csrf_origins"], ["https://padly.onrender.com"])

    def test_configured_unwritable_media_root_falls_back_to_writable_directory(self):
        with TemporaryDirectory() as temp_dir:
            blocked_media_root = Path(temp_dir) / "blocked-media-root"
            blocked_media_root.write_text("not a directory", encoding="utf-8")
            fallback_root = Path(temp_dir) / "fallback-media-root"

            result = self._run_python_subprocess(
                (
                    "import json; import vibecoders.settings as settings; "
                    "print(json.dumps({'media_root': str(settings.MEDIA_ROOT), "
                    "'fallback_used': settings.MEDIA_ROOT_FALLBACK_USED}))"
                ),
                extra_env={
                    "DJANGO_MEDIA_ROOT": str(blocked_media_root),
                    "DJANGO_MEDIA_FALLBACK_ROOT": str(fallback_root),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["media_root"], str(fallback_root.resolve()))
            self.assertTrue(payload["fallback_used"])
            self.assertTrue(fallback_root.is_dir())

    @unittest.skipUnless(HAS_DJ_DATABASE_URL, "dj-database-url is required for production DATABASE_URL settings tests.")
    def test_production_without_configured_media_root_uses_ephemeral_media_directory(self):
        result = self._run_python_subprocess(
            (
                "import json; import vibecoders.settings as settings; "
                "print(json.dumps({'media_root': str(settings.MEDIA_ROOT), "
                "'fallback_used': settings.MEDIA_ROOT_FALLBACK_USED}))"
            ),
            extra_env={
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "padly-production-secret-key-2026-04-27-render-no-disk-12345",
                "DJANGO_ALLOWED_HOSTS": "padly.example.com",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://padly.example.com",
                "DATABASE_URL": "postgresql://user:pass@localhost:5432/padly",
                "CHANNEL_REDIS_URL": "redis://localhost:6379/0",
                "CACHE_REDIS_URL": "redis://localhost:6379/1",
                "DJANGO_MEDIA_ROOT": None,
                "DJANGO_MEDIA_FALLBACK_ROOT": None,
            },
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["media_root"], str(Path("/tmp/padly-media").resolve()))
        self.assertFalse(payload["fallback_used"])

    def test_render_deployment_artifacts_are_checked_in(self):
        repo_root = Path(__file__).resolve().parents[2]
        python_version_path = repo_root / ".python-version"
        build_script_path = repo_root / "build.sh"
        start_script_path = repo_root / "start.sh"
        render_yaml_path = repo_root / "render.yaml"

        self.assertTrue(python_version_path.exists())
        self.assertEqual(python_version_path.read_text(encoding="utf-8").strip(), "3.12.5")

        self.assertTrue(build_script_path.exists())
        self.assertTrue(os.access(build_script_path, os.X_OK))
        build_script = build_script_path.read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements.txt", build_script)
        self.assertIn("python manage.py check --deploy", build_script)
        self.assertIn("python manage.py collectstatic --no-input", build_script)

        self.assertTrue(start_script_path.exists())
        self.assertTrue(os.access(start_script_path, os.X_OK))
        start_script = start_script_path.read_text(encoding="utf-8")
        self.assertNotIn("python manage.py migrate --noinput", start_script)
        self.assertIn('exec daphne -b 0.0.0.0 -p "${PORT:?PORT is required}" vibecoders.asgi:application', start_script)

        self.assertTrue(render_yaml_path.exists())
        render_yaml = render_yaml_path.read_text(encoding="utf-8")
        self.assertIn("buildCommand: ./build.sh", render_yaml)
        self.assertIn("preDeployCommand: python manage.py migrate", render_yaml)
        self.assertIn("startCommand: ./start.sh", render_yaml)
        self.assertIn("healthCheckPath: /healthz/", render_yaml)
        self.assertIn("DJANGO_MEDIA_ROOT", render_yaml)
        self.assertIn("value: /tmp/padly-media", render_yaml)
        self.assertIn("DJANGO_MEDIA_FALLBACK_ROOT", render_yaml)
        self.assertNotIn("\n    disk:", render_yaml)
        self.assertNotIn("mountPath: /var/data/padly-media", render_yaml)

    @unittest.skipUnless(HAS_DJ_DATABASE_URL, "dj-database-url is required for production DATABASE_URL settings tests.")
    def test_asgi_application_imports_cleanly_with_production_like_environment(self):
        result = self._run_python_subprocess(
            "import vibecoders.asgi; print('ok')",
            extra_env={
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "padly-production-secret-key-2026-04-19-render-check-12345",
                "DJANGO_ALLOWED_HOSTS": "padly.example.com",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://padly.example.com",
                "DATABASE_URL": "postgresql://user:pass@localhost:5432/padly",
                "CHANNEL_REDIS_URL": "redis://localhost:6379/0",
                "CACHE_REDIS_URL": "redis://localhost:6379/1",
            },
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_ci_workflow_keeps_quality_gates_lockfile_check_and_e2e_job(self):
        repo_root = Path(__file__).resolve().parents[2]
        workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("name: Unit and Checks", workflow)
        self.assertIn("name: Browser E2E", workflow)
        self.assertIn("needs: unit", workflow)
        self.assertIn("- run: pip install -r requirements.txt", workflow)
        self.assertIn("- run: pip-compile --quiet --dry-run --strip-extras requirements.in", workflow)
        self.assertIn("- run: ruff check .", workflow)
        self.assertIn("- run: ruff format --check .", workflow)
        self.assertIn("- run: python manage.py check", workflow)
        self.assertIn("- run: python manage.py makemigrations --check --dry-run", workflow)
        self.assertIn("- run: python manage.py test", workflow)
        self.assertIn("- run: python -m playwright install --with-deps chromium", workflow)
        self.assertIn("- run: python manage.py test e2e_tests", workflow)
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
            env["DJANGO_DISABLE_DOTENV"] = "1"
            env["PYTHONPATH"] = os.pathsep.join([temp_dir, str(repo_root)])
            if database_url:
                env["DATABASE_URL"] = database_url
            else:
                env["DATABASE_URL"] = ""

            return subprocess.run(
                [*PYTHON_SUBPROCESS_PREFIX, sys.executable, "-c", command],
                capture_output=True,
                check=False,
                cwd=repo_root,
                env=env,
                text=True,
            )

    def _run_python_subprocess(self, command, *, extra_env=None):
        repo_root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env["DJANGO_DEBUG"] = "true"
        env["DJANGO_DISABLE_DOTENV"] = "1"
        env["DJANGO_SETTINGS_MODULE"] = "vibecoders.settings"
        env["PYTHONPATH"] = str(repo_root)
        for key, value in (extra_env or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value

        return subprocess.run(
            [*PYTHON_SUBPROCESS_PREFIX, sys.executable, "-c", command],
            capture_output=True,
            check=False,
            cwd=repo_root,
            env=env,
            text=True,
        )
