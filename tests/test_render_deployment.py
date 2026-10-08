"""
Comprehensive Automated Test Suite: Render Deployment & Configuration Hardening
================================================================================
Verifies:
1. Local data root default (.envcore)
2. Configurable Render data root (CLIVERSE_DATA_ROOT)
3. Database and persistent directory path auto-creation
4. Production /api/health endpoint fields and status
5. Frontend static asset serving from frontend/dist
6. Cloud execution restriction under RENDER=true
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

import api
from api import (
    create_app,
    get_data_root,
    is_render_environment,
    ensure_storage_directories,
    configure_services,
)


class TestRenderDeploymentHardening(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.custom_root = Path(self.temp_dir.name).resolve()
        # Clean environment overrides
        self.orig_data_root = os.environ.get("CLIVERSE_DATA_ROOT")
        self.orig_render = os.environ.get("RENDER")

    def tearDown(self):
        if self.orig_data_root is not None:
            os.environ["CLIVERSE_DATA_ROOT"] = self.orig_data_root
        else:
            os.environ.pop("CLIVERSE_DATA_ROOT", None)

        if self.orig_render is not None:
            os.environ["RENDER"] = self.orig_render
        else:
            os.environ.pop("RENDER", None)

        # Restore default services
        configure_services()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_local_data_root_default(self):
        """Verifies local default data root points to .envcore."""
        os.environ.pop("CLIVERSE_DATA_ROOT", None)
        os.environ.pop("RENDER", None)
        root = get_data_root()
        self.assertEqual(root, (BASE_DIR / ".envcore").resolve())
        self.assertFalse(is_render_environment())

    def test_configurable_render_data_root(self):
        """Verifies CLIVERSE_DATA_ROOT env var configures the data root."""
        os.environ["CLIVERSE_DATA_ROOT"] = str(self.custom_root)
        root = get_data_root()
        self.assertEqual(root, self.custom_root)

        # Configure services to use the custom root
        applied_root = configure_services(self.custom_root)
        self.assertEqual(applied_root, self.custom_root)
        self.assertEqual(api.DATA_ROOT, self.custom_root)
        self.assertEqual(api.STORAGE_DIRS["memory"], self.custom_root / "memory")
        self.assertEqual(api.STORAGE_DIRS["sessions"], self.custom_root / "sessions")
        self.assertEqual(api.STORAGE_DIRS["rules_global"], self.custom_root / "rules" / "global")
        self.assertEqual(api.STORAGE_DIRS["identities"], self.custom_root / "identities")

    def test_database_path_creation(self):
        """Verifies missing storage directories are automatically created."""
        target_dir = self.custom_root / "nested" / "sub" / "storage"
        self.assertFalse(target_dir.exists())

        dirs = ensure_storage_directories(target_dir)
        self.assertTrue(target_dir.exists())
        self.assertTrue(dirs["memory"].exists())
        self.assertTrue(dirs["sessions"].exists())
        self.assertTrue(dirs["rules_global"].exists())
        self.assertTrue(dirs["identities"].exists())
        self.assertTrue(dirs["audit"].exists())
        self.assertTrue(dirs["secrets"].exists())
        self.assertTrue(dirs["governance"].exists())

    def test_health_endpoint(self):
        """Verifies /api/health returns comprehensive production health metrics."""
        app = create_app(data_root=self.custom_root)
        client = TestClient(app)

        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "HEALTHY")
        self.assertEqual(data["version"], "2.0.0")
        self.assertIn("environment", data)
        self.assertIn("storage", data)
        self.assertTrue(data["storage"]["writable"])
        self.assertEqual(data["storage"]["data_root"], str(self.custom_root))
        self.assertIn("subsystems", data)
        self.assertIn("memory", data["subsystems"])
        self.assertIn("rules", data["subsystems"])
        self.assertIn("laya", data["subsystems"])
        self.assertIn("security", data["subsystems"])
        self.assertIn("git", data["subsystems"])
        self.assertIn("cli_execution", data["subsystems"])

    def test_render_environment_detection_in_health(self):
        """Verifies that RENDER=true reflects in /api/health and disables remote execution."""
        os.environ["RENDER"] = "true"
        os.environ["CLIVERSE_DATA_ROOT"] = str(self.custom_root)

        app = create_app(data_root=self.custom_root)
        client = TestClient(app)

        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["environment"], "render")
        self.assertTrue(data["is_render"])
        self.assertEqual(data["subsystems"]["cli_execution"]["mode"], "LOCAL_ONLY")
        self.assertFalse(data["subsystems"]["cli_execution"]["available"])

    def test_render_cli_execution_restriction(self):
        """Verifies that on Render, CLI execution requests are safely refused with explanation."""
        os.environ["RENDER"] = "true"
        os.environ["CLIVERSE_DATA_ROOT"] = str(self.custom_root)

        app = create_app(data_root=self.custom_root)
        client = TestClient(app)

        # Provider list on Render reports not installed / local only
        p_res = client.get("/api/providers")
        self.assertEqual(p_res.status_code, 200)
        providers = p_res.json()
        for p in providers:
            self.assertFalse(p["is_available"])
            self.assertEqual(p["status"], "NOT_INSTALLED")
            self.assertIn("LOCAL CLI EXECUTION AVAILABLE", p["error_message"])

        # Execution attempt is gracefully blocked
        exec_res = client.post("/api/providers/execute", json={
            "provider": "claude",
            "task": "Test task on cloud",
        })
        self.assertEqual(exec_res.status_code, 200)
        res_data = exec_res.json()
        self.assertFalse(res_data["ok"])
        self.assertEqual(res_data["status"], "cloud_execution_unsupported")
        self.assertEqual(res_data["trust_gate_decision"], "BLOCK")
        self.assertIn("LOCAL CLI EXECUTION AVAILABLE", res_data["error_message"])

    def test_frontend_static_serving(self):
        """Verifies that index.html is served from frontend/dist when present."""
        frontend_dist = BASE_DIR / "frontend" / "dist"
        if not frontend_dist.is_dir():
            self.skipTest("frontend/dist is not built; build with npm run build")

        app = create_app(data_root=self.custom_root)
        client = TestClient(app)

        # Root should return HTML with 200 OK
        res = client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("<html", res.text.lower())

        # Non-API path should route to SPA index.html
        res_spa = client.get("/providers")
        self.assertEqual(res_spa.status_code, 200)
        self.assertIn("text/html", res_spa.headers.get("content-type", ""))

        # API paths must not be hijacked
        res_api = client.get("/api/nonexistent_route_test")
        self.assertEqual(res_api.status_code, 404)


if __name__ == "__main__":
    unittest.main()
