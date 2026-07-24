"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_CASSANDRA_.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_PREFIX = "RUVIC_CASSANDRA_"


@dataclass(frozen=True)
class CassandraConfig:
    """Parámetros de conexión a Apache Cassandra."""

    hosts: list[str]
    port: int
    username: str
    password: str
    local_datacenter: str
    connect_timeout: int = 10

    @classmethod
    def from_env(cls) -> "CassandraConfig":
        """Construye la configuración desde las variables RUVIC_CASSANDRA_*.

        Raises:
            ValueError: si falta alguna variable obligatoria.

        Ejemplo:
            >>> config = CassandraConfig.from_env()
            >>> config.hosts
            ['db.empresa.com']
        """
        missing = [
            f"{ENV_PREFIX}{name}"
            for name in ("HOSTS", "USERNAME", "PASSWORD", "LOCAL_DATACENTER")
            if not os.environ.get(f"{ENV_PREFIX}{name}")
        ]
        if missing:
            raise ValueError(
                "Faltan variables de entorno del conector cassandra: "
                + ", ".join(missing)
                + ". Configura el conector en Settings → Conectores."
            )
        hosts = [h.strip() for h in os.environ[f"{ENV_PREFIX}HOSTS"].split(",") if h.strip()]
        return cls(
            hosts=hosts,
            port=int(os.environ.get(f"{ENV_PREFIX}PORT", "9042")),
            username=os.environ[f"{ENV_PREFIX}USERNAME"],
            password=os.environ[f"{ENV_PREFIX}PASSWORD"],
            local_datacenter=os.environ[f"{ENV_PREFIX}LOCAL_DATACENTER"],
            connect_timeout=int(os.environ.get(f"{ENV_PREFIX}CONNECT_TIMEOUT", "10")),
        )
