"""Prueba de conexión estándar del conector cassandra.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_CASSANDRA_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Conecta a Cassandra y ejecuta una consulta trivial usando las env
    vars RUVIC_CASSANDRA_*."""
    try:
        from ruvic_cassandra_connector import (
            CassandraAuthError,
            CassandraClient,
            CassandraDataError,
            CassandraNetworkError,
        )
    except ImportError:
        return (
            False,
            (
                "La librería ruvic-cassandra-connector no está instalada. "
                "Instala con: pip install git+https://github.com/Dgirto/"
                "Cassandra.git#subdirectory=lib"
            ),
        )

    try:
        client = CassandraClient()  # valida que existan las env vars
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except CassandraAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except CassandraNetworkError as exc:
        return False, f"Error de red: {exc}"
    except CassandraDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # noqa: BLE001 - red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (
        True,
        f"Conexión exitosa a Cassandra {client.config.hosts}",
    )


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
