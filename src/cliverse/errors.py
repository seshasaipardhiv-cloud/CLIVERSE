"""Stable CLI-facing errors."""


class CliverseError(Exception):
    """An expected error that can be safely shown to a CLI user."""

    code = "CLIVERSE_ERROR"
    suggestion = "Review the input and try again."

    def __init__(self, message: str) -> None:
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": str(self),
            "suggestion": self.suggestion,
        }


class InvalidProjectRoot(CliverseError):
    code = "INVALID_PROJECT_ROOT"
    suggestion = "Pass an existing project directory with --root."


class EnvironmentAlreadyInitialized(CliverseError):
    code = "ENVIRONMENT_ALREADY_INITIALIZED"
    suggestion = "Inspect the existing .envcore/config.json; init never overwrites it."


class InvalidEnvironment(CliverseError):
    code = "INVALID_ENVIRONMENT"
    suggestion = "Check that .envcore/config.json is valid and inside the project root."
