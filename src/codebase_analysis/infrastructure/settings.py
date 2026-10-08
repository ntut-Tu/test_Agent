"""Load values-style YAML into validated settings with masked secret fields."""

from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SettingsError(ValueError):
    """Invalid configuration, reported without secret values."""


class _SettingsSection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class LlmSettings(_SettingsSection):
    """LangChain provider initialization settings.

    Attributes:
        provider: LangChain model_provider identifier.
        model: Model identifier understood by the selected provider.
        api_key: Optional credential passed as api_key when nonempty.
        options: Additional provider keyword arguments, excluded from repr.
    """

    provider: NonEmptyString
    model: NonEmptyString
    api_key: SecretStr = SecretStr("")
    options: dict[str, Any] = Field(default_factory=dict, repr=False)

    @model_validator(mode="after")
    def validate_options(self) -> "LlmSettings":
        """Reject options that override reserved model initialization fields.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: options includes a reserved parameter.
        """
        reserved = {"model", "model_provider", "api_key", "configurable_fields", "config_prefix"}
        if reserved.intersection(self.options):
            raise ValueError("options contains reserved model initialization parameters")
        return self


class CodeHostSettings(_SettingsSection):
    """Connection settings for the repository hosting the PR/MR.

    Attributes:
        provider: Either github or gitlab.
        repository: GitHub owner/repo, or GitLab project path or ID as a string.
        api_url: API root override; None selects the provider's public API.
        token: Access token; empty for unauthenticated requests.
    """

    provider: Literal["github", "gitlab"]
    repository: NonEmptyString
    api_url: NonEmptyString | None = None
    token: SecretStr = SecretStr("")


class JenkinsSettings(_SettingsSection):
    """Location and optional Basic authentication for a coverage artifact.

    Attributes:
        artifact_url: URL of one build's JaCoCo or Cobertura XML artifact.
        username: Jenkins user; empty for an unauthenticated request.
        api_token: API token supplied together with username.
        trace_url: Optional version-1 per-test Java trace artifact URL.
        metadata_url: Coverage provenance JSON; required when trace is absent.
    """

    artifact_url: NonEmptyString
    username: str = ""
    api_token: SecretStr = SecretStr("")
    trace_url: NonEmptyString | None = None
    metadata_url: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_credentials(self) -> "JenkinsSettings":
        """Require username and API token to be either both set or both empty.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: Only one credential is supplied.
        """
        if bool(self.username) != bool(self.api_token.get_secret_value()):
            raise ValueError("username and api_token must be supplied together")
        return self


class AnalysisSettings(_SettingsSection):
    """Collection limits applied before model analysis.

    Attributes:
        max_test_files: Positive maximum number of test candidates to retrieve.
    """

    max_test_files: int = Field(default=20, ge=1)


class CollectionSettings(_SettingsSection):
    """Configuration required by remote collection without a model.

    Attributes:
        code_host: Repository API connection.
        jenkins: Coverage artifact location and credentials.
        analysis: Collection limits, using defaults when the section is absent.
    """

    code_host: CodeHostSettings
    jenkins: JenkinsSettings
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)


class Settings(CollectionSettings):
    """Complete values configuration, extending collection with model settings.

    Attributes:
        llm: Model provider, model name, and credentials.
        code_host: Repository API connection.
        jenkins: Coverage artifact location and credentials.
        analysis: Collection limits.
    """

    llm: LlmSettings


_SettingsType = TypeVar("_SettingsType", bound=_SettingsSection)


def _read_values(path: str | Path) -> Any:
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError:
        raise SettingsError("Cannot read values file") from None
    except (yaml.YAMLError, UnicodeError):
        raise SettingsError("Values file must contain valid UTF-8 YAML") from None


def _validate_values(data: Any, schema: type[_SettingsType]) -> _SettingsType:
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        # Locations only: validation input and messages may contain credentials.
        fields = ", ".join(".".join(map(str, error["loc"])) or "root" for error in exc.errors())
        raise SettingsError(f"Invalid values configuration; check: {fields}") from None


def load_settings(path: str | Path) -> Settings:
    """Read and validate all values sections without changing process environment.

    Args:
        path: YAML file path, relative to the caller's working directory if needed.

    Returns:
        Complete settings with masked credential fields.

    Raises:
        SettingsError: Reading, YAML parsing, or configuration validation fails.
    """
    return _validate_values(_read_values(path), Settings)


def load_collection_settings(path: str | Path) -> CollectionSettings:
    """Read collection settings while ignoring the unused llm section.

    Args:
        path: YAML file path, relative to the caller's working directory if needed.

    Returns:
        Collection settings; llm may be absent or contain blank placeholders.

    Raises:
        SettingsError: Reading, YAML parsing, or collection validation fails.
    """
    data = _read_values(path)
    if isinstance(data, dict):
        data = {key: value for key, value in data.items() if key != "llm"}
    return _validate_values(data, CollectionSettings)
