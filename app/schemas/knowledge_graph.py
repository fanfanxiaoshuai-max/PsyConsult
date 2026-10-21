from typing import Any
from pydantic import BaseModel, Field

class GraphSearch(BaseModel):
    version: str
    items: list[dict[str, Any]]
    total: int
    truncated: bool

class GraphNeighborhood(BaseModel):
    version: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    sources: list[dict[str, Any]] = Field(default_factory=list)
    total: int
    truncated: bool
    message: str
