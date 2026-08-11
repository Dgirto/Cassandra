"""Cliente de consulta de solo lectura para Apache Cassandra.

Capacidades:
- list_keyspaces_and_tables(): listar keyspaces y sus tablas.
- read_rows():                 leer filas de una tabla con límite.
- execute_cql():                ejecutar una sentencia CQL de solo lectura.

Las credenciales SIEMPRE provienen de variables de entorno RUVIC_CASSANDRA_*
(ver config.CassandraConfig.from_env). Prohibido hardcodearlas.
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any

# cassandra-driver decide su reactor de I/O por defecto al importar
# cassandra.cluster, probando (en orden) gevent, eventlet, la extensión C
# de libev y asyncore. Desde Python 3.12 asyncore ya no existe en el
# stdlib y libev requiere un compilador C, así que en cualquier entorno
# moderno sin build tools la importación falla salvo que gevent ya esté
# parcheado — por eso el patch va antes de tocar el paquete cassandra.
from gevent import monkey  # type: ignore[import-untyped]

monkey.patch_all()

from cassandra import (  # type: ignore[import-untyped]
    InvalidRequest,
    OperationTimedOut,
    Unauthorized,
)
from cassandra.auth import PlainTextAuthProvider  # type: ignore[import-untyped]
from cassandra.cluster import (  # type: ignore[import-untyped]
    Cluster,
    NoHostAvailable,
    Session,
)
from cassandra.io.geventreactor import GeventConnection  # type: ignore[import-untyped]
from cassandra.policies import DCAwareRoundRobinPolicy  # type: ignore[import-untyped]

from .config import CassandraConfig
from .exceptions import (
    CassandraAuthError,
    CassandraConnectorError,
    CassandraDataError,
    CassandraNetworkError,
)
from .logging_utils import get_logger

_SYSTEM_KEYSPACES = {
    "system",
    "system_schema",
    "system_auth",
    "system_distributed",
    "system_traces",
    "system_views",
    "system_virtual_schema",
}
_MAX_LIMIT = 1_000


def _validate_select(query: str) -> str:
    query = (query or "").strip()
    if not query:
        raise CassandraDataError("La consulta CQL no puede estar vacía.")
    if not query.rstrip(";").strip().upper().startswith("SELECT"):
        raise CassandraDataError(
            "Solo se permiten sentencias SELECT. La operación solicitada "
            "fue rechazada por seguridad."
        )
    return query


class CassandraClient:
    """Cliente de consulta de solo lectura sobre un clúster de Cassandra.

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_CASSANDRA_* (comportamiento
            estándar en el runtime de la plataforma).

    Ejemplo:
        >>> client = CassandraClient()  # lee RUVIC_CASSANDRA_* del entorno
        >>> client.list_keyspaces_and_tables()
        {'ventas': ['pedidos', 'clientes']}
    """

    def __init__(self, config: CassandraConfig | None = None) -> None:
        self.config = config or CassandraConfig.from_env()
        self._logger = get_logger()
        self._cluster: Cluster | None = None
        self._session: Session | None = None
        self._scb_path: Path | None = None

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _build_cluster(self) -> Cluster:
        if self.config.is_astra:
            # Astra no expone contact points directos: el bundle trae los
            # certificados TLS y el endpoint del proxy seguro, y el
            # usuario/rol se reemplaza por el literal "token".
            raw_bundle = base64.b64decode(self.config.secure_connect_bundle_b64 or "")
            fd, tmp_name = tempfile.mkstemp(suffix=".zip")
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(raw_bundle)
            self._scb_path = Path(tmp_name)
            auth_provider = PlainTextAuthProvider(username="token", password=self.config.token)
            return Cluster(
                cloud={"secure_connect_bundle": str(self._scb_path)},
                auth_provider=auth_provider,
                connect_timeout=self.config.connect_timeout,
                connection_class=GeventConnection,
            )
        auth_provider = PlainTextAuthProvider(
            username=self.config.username, password=self.config.password
        )
        return Cluster(
            contact_points=self.config.hosts,
            port=self.config.port,
            auth_provider=auth_provider,
            load_balancing_policy=DCAwareRoundRobinPolicy(
                local_dc=self.config.local_datacenter
            ),
            connect_timeout=self.config.connect_timeout,
            protocol_version=4,
            connection_class=GeventConnection,
        )

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        self._cluster = self._build_cluster()
        try:
            self._session = self._cluster.connect()
        except NoHostAvailable as exc:
            errors = getattr(exc, "errors", {}) or {}
            # exc.errors normalmente es un dict {host: excepción}, pero
            # cuando la política de balanceo descarta todos los hosts antes
            # de intentar conectar (ej. local_datacenter que no existe en
            # el clúster), el driver lo entrega como lista, no como dict.
            error_values = errors.values() if isinstance(errors, dict) else errors
            if any(isinstance(e, Unauthorized) for e in error_values):
                raise CassandraAuthError(
                    "Credenciales inválidas o sin permiso suficiente sobre "
                    "el clúster."
                ) from exc
            target = "Astra DB" if self.config.is_astra else str(self.config.hosts)
            raise CassandraNetworkError(
                f"No se pudo alcanzar ningún nodo de {target}. "
                "Revisa las credenciales/bundle y el datacenter local configurado."
            ) from exc
        except OperationTimedOut as exc:
            raise CassandraNetworkError(
                "Timeout al conectar con el clúster Cassandra."
            ) from exc
        return self._session

    def ping(self) -> bool:
        """Verifica la conexión ejecutando una consulta trivial al sistema.

        Returns:
            True si la conexión funciona.

        Raises:
            CassandraAuthError / CassandraNetworkError / CassandraDataError
            según el fallo.
        """
        try:
            self._get_session().execute("SELECT release_version FROM system.local")
        except CassandraConnectorError:
            raise
        except Exception as exc:  # errores no mapeados del driver
            raise CassandraNetworkError(f"No se pudo conectar: {exc}") from exc
        target = "Astra DB" if self.config.is_astra else self.config.hosts
        self._logger.info("Ping exitoso a Cassandra %s", target)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: listar keyspaces y tablas
    # ------------------------------------------------------------------ #

    def list_keyspaces_and_tables(self, include_system: bool = False) -> dict[str, list[str]]:
        """Lista los keyspaces del clúster y las tablas de cada uno.

        Args:
            include_system: si True, incluye los keyspaces internos del
                sistema (`system`, `system_schema`, etc.). Default False.

        Returns:
            Dict {keyspace: [tabla, ...]}.

        Ejemplo:
            >>> client.list_keyspaces_and_tables()
            {'ventas': ['pedidos', 'clientes']}
        """
        session = self._get_session()
        try:
            keyspace_rows = session.execute(
                "SELECT keyspace_name FROM system_schema.keyspaces"
            )
            keyspaces = [
                row.keyspace_name
                for row in keyspace_rows
                if include_system or row.keyspace_name not in _SYSTEM_KEYSPACES
            ]
            result: dict[str, list[str]] = {}
            for keyspace in keyspaces:
                table_rows = session.execute(
                    "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
                    (keyspace,),
                )
                result[keyspace] = [row.table_name for row in table_rows]
        except Exception as exc:
            raise CassandraDataError(f"Error al listar keyspaces/tablas: {exc}") from exc

        self._logger.info("Se listaron %d keyspaces", len(result))
        return result

    # ------------------------------------------------------------------ #
    # Capacidad 2: leer filas de una tabla
    # ------------------------------------------------------------------ #

    def read_rows(self, keyspace: str, table: str, limit: int = 100) -> list[dict[str, Any]]:
        """Lee filas de una tabla con un límite.

        Args:
            keyspace: nombre del keyspace.
            table: nombre de la tabla.
            limit: máximo de filas a retornar (default 100, máximo 1000).

        Returns:
            Lista de dicts, una por fila.

        Ejemplo:
            >>> client.read_rows("ventas", "pedidos", limit=10)
            [{'id': 1, 'cliente': 'ACME'}]
        """
        keyspace = (keyspace or "").strip()
        table = (table or "").strip()
        if not keyspace or not table:
            raise CassandraDataError("keyspace y table no pueden estar vacíos.")
        limit = max(1, min(int(limit), _MAX_LIMIT))
        session = self._get_session()
        try:
            rows = session.execute(f'SELECT * FROM "{keyspace}"."{table}" LIMIT {limit}')
            result = [dict(row._asdict()) for row in rows]
        except InvalidRequest as exc:
            raise CassandraDataError(
                f'La tabla "{keyspace}.{table}" no existe o la consulta es inválida: {exc}'
            ) from exc
        except Exception as exc:
            raise CassandraDataError(f"Error al leer filas: {exc}") from exc

        self._logger.info('Leídas %d filas de "%s.%s"', len(result), keyspace, table)
        return result

    # ------------------------------------------------------------------ #
    # Capacidad 3: ejecutar CQL de solo lectura
    # ------------------------------------------------------------------ #

    def execute_cql(self, query: str, keyspace: str | None = None) -> list[dict[str, Any]]:
        """Ejecuta una sentencia CQL de solo lectura (SELECT).

        Args:
            query: sentencia CQL. Debe empezar con SELECT; cualquier otra
                cosa (INSERT, UPDATE, DELETE, CREATE, DROP, ALTER) se
                rechaza a nivel de código.
            keyspace: keyspace en el que ejecutar la consulta si la
                sentencia no lo califica explícitamente (opcional).

        Returns:
            Lista de dicts, una por fila del resultado.

        Ejemplo:
            >>> client.execute_cql("SELECT * FROM pedidos LIMIT 5", keyspace="ventas")
            [{'id': 1, 'cliente': 'ACME'}]
        """
        query = _validate_select(query)
        session = self._get_session()
        if keyspace:
            session.set_keyspace(keyspace)
        try:
            rows = session.execute(query)
            result = [dict(row._asdict()) for row in rows]
        except InvalidRequest as exc:
            raise CassandraDataError(f"Consulta CQL inválida: {exc}") from exc
        except Exception as exc:
            raise CassandraDataError(f"Error al ejecutar la consulta: {exc}") from exc

        self._logger.info("execute_cql devolvió %d filas", len(result))
        return result
