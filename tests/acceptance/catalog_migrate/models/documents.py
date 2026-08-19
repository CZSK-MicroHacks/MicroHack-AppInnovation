"""Pydantic models for migration result fragments."""

from pydantic import BaseModel, ConfigDict, Field


class DatabaseTool(BaseModel):
    """Identify one external database migration tool and exact version."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class Artifact(BaseModel):
    """Describe one immutable database migration artifact."""

    model_config = ConfigDict(extra="forbid")

    format: str
    exportTool: DatabaseTool
    importTool: DatabaseTool
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0)
