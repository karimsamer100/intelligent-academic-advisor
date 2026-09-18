"""Academic dataset version metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    """Identity of the structured academic dataset used by a result."""

    version: str
    source: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("dataset version must be a non-empty string")
        for name in ("source", "revision"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string when provided")

    @property
    def source_revision(self) -> str | None:
        return self.revision

    def to_dict(self) -> dict[str, str]:
        values = {"version": self.version}
        if self.source is not None:
            values["source"] = self.source
        if self.revision is not None:
            values["revision"] = self.revision
        return values


DatasetVersionMetadata = DatasetVersion
