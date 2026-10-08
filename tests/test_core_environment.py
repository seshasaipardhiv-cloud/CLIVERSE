import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.environment import ProjectEnvironment
from cliverse.errors import (
    EnvironmentAlreadyInitialized,
    InvalidEnvironment,
    InvalidProjectRoot,
)


class ProjectEnvironmentTests(unittest.TestCase):
    def test_initialize_and_load_project_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialized = ProjectEnvironment.initialize(root)
            loaded = ProjectEnvironment.load(root)

            self.assertEqual(initialized.config_path, root / ".envcore" / "config.json")
            self.assertEqual(loaded.config["environment_id"], initialized.config["environment_id"])
            self.assertEqual(json.loads(initialized.config_path.read_text())["schema_version"], 1)

    def test_initialize_does_not_overwrite_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ".envcore" / "config.json"
            config.parent.mkdir()
            config.parent.chmod(0o700)
            config.write_text('{"owner":"existing"}', encoding="utf-8")

            with self.assertRaises(EnvironmentAlreadyInitialized):
                ProjectEnvironment.initialize(root)

            self.assertEqual(config.read_text(encoding="utf-8"), '{"owner":"existing"}')

    def test_rejects_missing_project_root(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-created"
            with self.assertRaises(InvalidProjectRoot):
                ProjectEnvironment.initialize(missing)

    def test_load_rejects_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".envcore" / "config.json"
            config.parent.mkdir()
            config.write_text("{}", encoding="utf-8")

            with self.assertRaises(InvalidEnvironment):
                ProjectEnvironment.load(directory)

    @unittest.skipUnless(os.name == "posix", "POSIX permissions required")
    def test_initialize_rejects_public_metadata_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata_dir = Path(directory) / ".envcore"
            metadata_dir.mkdir(mode=0o755)
            metadata_dir.chmod(0o755)

            with self.assertRaises(InvalidEnvironment):
                ProjectEnvironment.initialize(directory)

    def test_cli_init_and_status_emit_json(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            init = subprocess.run(
                [sys.executable, str(repository / "env.py"), "init", "--root", directory],
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                [sys.executable, str(repository / "env.py"), "status", "--root", directory],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertTrue(json.loads(init.stdout)["ok"])
            self.assertEqual(
                json.loads(init.stdout)["environment_id"],
                json.loads(status.stdout)["environment_id"],
            )


if __name__ == "__main__":
    unittest.main()
