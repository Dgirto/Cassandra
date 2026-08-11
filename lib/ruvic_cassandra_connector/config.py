"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_CASSANDRA_.

Soporta dos modos de conexión (ver manifest.json → auth_modes):
- "user_password": clúster self-hosted, host:puerto directo.
- "astra": DataStax Astra DB, vía Secure Connect Bundle + token.
El modo se determina por qué variables llegaron llenas, no por un campo
explícito: la presencia de SECURE_CONNECT_BUNDLE_B64 activa el modo Astra.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_PREFIX = "RUVIC_CASSANDRA_"


@dataclass(frozen=True)
class CassandraConfig:
    """Parámetros de conexión a Apache Cassandra o Astra DB."""

    connect_timeout: int = 10

    # Modo "user_password" (self-hosted)
    hosts: list[str] | None = None
    port: int = 9042
    username: str | None = None
    password: str | None = None
    local_datacenter: str | None = None

    # Modo "astra" (DataStax Astra DB)
    secure_connect_bundle_b64: str | None = None
    token: str | None = None

    @property
    def is_astra(self) -> bool:
        return self.secure_connect_bundle_b64 is not None

    @classmethod
    def from_env(cls) -> CassandraConfig:
        """Construye la configuración desde las variables RUVIC_CASSANDRA_*.

        Raises:
            ValueError: si falta alguna variable obligatoria del modo
                detectado.

        Ejemplo:
            >>> config = CassandraConfig.from_env()
            >>> config.hosts
            ['db.empresa.com']
        """
        connect_timeout = int(os.environ.get(f"{ENV_PREFIX}CONNECT_TIMEOUT", "10"))

        scb_b64 = os.environ.get(f"{ENV_PREFIX}SECURE_CONNECT_BUNDLE_B64") or None
        if scb_b64:
            missing = [
                f"{ENV_PREFIX}{name}"
                for name in ("SECURE_CONNECT_BUNDLE_B64", "TOKEN")
                if not os.environ.get(f"{ENV_PREFIX}{name}")
            ]
            if missing:
                raise ValueError(
                    "Faltan variables de entorno del conector cassandra (modo Astra): "
                    + ", ".join(missing)
                    + ". Configura el conector en Settings → Conectores."
                )
            return cls(
                connect_timeout=connect_timeout,
                secure_connect_bundle_b64=scb_b64,
                token=os.environ[f"{ENV_PREFIX}TOKEN"],
            )

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
            connect_timeout=connect_timeout,
            hosts=hosts,
            port=int(os.environ.get(f"{ENV_PREFIX}PORT", "9042")),
            username=os.environ[f"{ENV_PREFIX}USERNAME"],
            password=os.environ[f"{ENV_PREFIX}PASSWORD"],
            local_datacenter=os.environ[f"{ENV_PREFIX}LOCAL_DATACENTER"],
        )
