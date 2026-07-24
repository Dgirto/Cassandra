"""Conector Ruvic de solo lectura para Apache Cassandra."""

from .client import CassandraClient
from .config import ENV_PREFIX, CassandraConfig
from .exceptions import (
    CassandraAuthError,
    CassandraConnectorError,
    CassandraDataError,
    CassandraNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "CassandraAuthError",
    "CassandraClient",
    "CassandraConfig",
    "CassandraConnectorError",
    "CassandraDataError",
    "CassandraNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"
