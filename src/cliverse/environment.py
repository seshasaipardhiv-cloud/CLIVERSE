"""Safe initialization and loading of a project-local CLIVERSE environment."""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import (
    EnvironmentAlreadyInitialized,
    InvalidEnvironment,
    InvalidProjectRoot,
)

CONFIG_NAME = "config.json"
METADATA_DIR_NAME = ".envcore"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProjectEnvironment:
    root: Path
    metadata_dir: Path
    config_path: Path
    config: dict[str, Any]

    @classmethod
    def initialize(cls, root: str | Path = ".") -> "ProjectEnvironment":
        project_root = Path(root).expanduser().resolve()
        if not project_root.exists() or not project_root.is_dir():
            raise InvalidProjectRoot(f"Project root is not an existing directory: {project_root}")

        metadata_dir = project_root / METADATA_DIR_NAME
        if metadata_dir.is_symlink():
            raise InvalidEnvironment(f"Refusing symlinked environment directory: {metadata_dir}")
        metadata_dir.mkdir(mode=0o700, exist_ok=True)

        config_path = metadata_dir / CONFIG_NAME
        config = {
            "schema_version": SCHEMA_VERSION,
            "environment_id": str(uuid.uuid4()),
            "project_root": str(project_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        encoded = (json.dumps(config, indent=2) + "\n").encode("utf-8")

        try:
            descriptor = os.open(
                config_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise EnvironmentAlreadyInitialized(
                f"Environment configuration already exists: {config_path}"
            ) from exc

        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

        return cls(
            root=project_root,
            metadata_dir=metadata_dir,
            config_path=config_path,
            config=config,
        )

    @classmethod
    def load(cls, root: str | Path = ".") -> "ProjectEnvironment":
        project_root = Path(root).expanduser().resolve()
        if not project_root.exists() or not project_root.is_dir():
            raise InvalidProjectRoot(f"Project root is not an existing directory: {project_root}")

        metadata_dir = project_root / METADATA_DIR_NAME
        config_path = metadata_dir / CONFIG_NAME
        if metadata_dir.is_symlink() or config_path.is_symlink():
            raise InvalidEnvironment("Environment configuration must not use symlinks.")
        if not metadata_dir.is_dir() or not config_path.is_file():
            raise InvalidEnvironment(f"No initialized environment found under {project_root}")

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InvalidEnvironment(f"Could not read environment configuration: {exc}") from exc

        if (
            not isinstance(config, dict)
            or config.get("schema_version") != SCHEMA_VERSION
            or config.get("project_root") != str(project_root)
            or not isinstance(config.get("environment_id"), str)
        ):
            raise InvalidEnvironment(f"Unsupported or invalid environment configuration: {config_path}")

        return cls(
            root=project_root,
            metadata_dir=metadata_dir,
            config_path=config_path,
            config=config,
        )
