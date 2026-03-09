"""Base connector interface.

All external data connectors inherit from this base class.
This keeps connectors swappable and testable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorResult:
    """Standardised result from any connector."""
    success: bool
    source: str  # connector name
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class BaseConnector(ABC):
    """Interface that every data connector must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable connector name."""
        ...

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> ConnectorResult:
        """Execute the connector and return a result."""
        ...
