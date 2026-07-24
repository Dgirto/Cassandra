"""Excepciones propias del conector Cassandra.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del driver subyacente.
"""


class CassandraConnectorError(Exception):
    """Error base del conector."""


class CassandraAuthError(CassandraConnectorError):
    """Credenciales inválidas o permisos insuficientes."""


class CassandraNetworkError(CassandraConnectorError):
    """No se pudo alcanzar el clúster (host/puerto/red/timeout)."""


class CassandraDataError(CassandraConnectorError):
    """La operación es válida pero el keyspace/tabla/consulta es inválida."""
