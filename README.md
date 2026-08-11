# Conector Cassandra (CON-056)

Conector Ruvic de consulta de solo lectura para Apache Cassandra. Permite
listar keyspaces y sus tablas, leer filas de una tabla con límite, y
ejecutar sentencias CQL de solo lectura (SELECT).

## Instalación

```bash
pip install git+https://github.com/Dgirto/Cassandra.git#subdirectory=lib
```

Python 3.10+. Dependencia única: `cassandra-driver>=3.29,<4.0`.

## Permisos requeridos en el clúster

Crea un rol dedicado de solo lectura (no reutilizar `cassandra` ni un rol
de aplicación):

```sql
CREATE ROLE ruvic_reader WITH PASSWORD = 'CAMBIA_ESTA_CONTRASEÑA' AND LOGIN = true;
GRANT SELECT ON KEYSPACE ventas TO ruvic_reader;
```

- `SELECT` sobre el/los keyspaces a exponer: necesario para
  `db.read_rows` y `db.execute_cql`. Otorga sobre keyspaces específicos
  en vez de todo el clúster si es posible.
- Listar keyspaces/tablas (`db.list_keyspaces_and_tables`) usa las
  tablas del sistema `system_schema`, legibles por cualquier rol
  autenticado.
- No se otorgan permisos de escritura (`MODIFY`) ni de administración
  (`CREATE`, `ALTER`, `DROP`, `AUTHORIZE`).

## Modos de conexión

El conector soporta dos modos (ver `manifest.json` → `auth_modes`). El
modo se detecta por qué variables llegan llenas: si
`RUVIC_CASSANDRA_SECURE_CONNECT_BUNDLE_B64` está presente se usa Astra;
si no, modo directo.

### Modo directo (`user_password`) — clúster self-hosted

Para un clúster alcanzable por host:puerto directo (VPN, red privada, IP
pública). **No aplica a DataStax Astra ni a otras bases de datos
administradas** que no exponen contact points directos.

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_CASSANDRA_HOSTS` | Sí | Nodos de contacto separados por coma |
| `RUVIC_CASSANDRA_PORT` | No (default `9042`) | Puerto |
| `RUVIC_CASSANDRA_USERNAME` | Sí | Usuario |
| `RUVIC_CASSANDRA_PASSWORD` | Sí | Contraseña |
| `RUVIC_CASSANDRA_LOCAL_DATACENTER` | Sí | Datacenter local (ver `nodetool status`) |
| `RUVIC_CASSANDRA_CONNECT_TIMEOUT` | No (default `10`) | Timeout de conexión en segundos |

### Modo Astra (`astra`) — DataStax Astra DB

Astra no expone host:puerto directo; requiere el Secure Connect Bundle
(certificados TLS + endpoint del proxy) y un Application Token.

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_CASSANDRA_SECURE_CONNECT_BUNDLE_B64` | Sí | El `.zip` descargado en Astra (Database → Connect → Drivers → Download SCB), codificado en base64 |
| `RUVIC_CASSANDRA_TOKEN` | Sí | Application Token generado en Astra (empieza con `AstraCS:`) |
| `RUVIC_CASSANDRA_CONNECT_TIMEOUT` | No (default `10`) | Timeout de conexión en segundos |

Para codificar el bundle en base64:

```bash
# Linux/macOS
base64 -w0 secure-connect-mi-db.zip > bundle.b64

# PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("secure-connect-mi-db.zip")) | Set-Content bundle.b64
```

## Pruebas locales

### Modo directo, con Docker (nodo único, autenticación con `PasswordAuthenticator`):

```bash
docker run -d --name cassandra-test \
  -e CASSANDRA_DC=datacenter1 \
  -p 9042:9042 \
  cassandra:5

# Espera ~1-2 min a que arranque, luego habilita autenticación y crea el rol
docker exec -it cassandra-test cqlsh -u cassandra -p cassandra \
  -e "CREATE ROLE ruvic_reader WITH PASSWORD = 'ruvic123' AND LOGIN = true;
      CREATE KEYSPACE ventas WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
      GRANT SELECT ON KEYSPACE ventas TO ruvic_reader;"
```

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_CASSANDRA_HOSTS=localhost
export RUVIC_CASSANDRA_PORT=9042
export RUVIC_CASSANDRA_USERNAME=ruvic_reader
export RUVIC_CASSANDRA_PASSWORD=ruvic123
export RUVIC_CASSANDRA_LOCAL_DATACENTER=datacenter1

python test_connection.py
python validate_local.py
```

Prueba también los casos de error (credenciales incorrectas, tabla
inexistente, sentencia no-SELECT rechazada) y verifica que los mensajes
sean claros.

### Modo Astra

```bash
export RUVIC_CASSANDRA_SECURE_CONNECT_BUNDLE_B64=$(base64 -w0 secure-connect-mi-db.zip)
export RUVIC_CASSANDRA_TOKEN='AstraCS:...'

python test_connection.py
python validate_local.py
```

## Notas de integración

- `execute_cql` valida a nivel de código que la sentencia empiece con
  `SELECT`; cualquier otra cosa (`INSERT`, `UPDATE`, `DELETE`, `CREATE`,
  `DROP`, `ALTER`, `TRUNCATE`) se rechaza antes de llegar a Cassandra.
- `list_keyspaces_and_tables` excluye por defecto los keyspaces internos
  del sistema (`system`, `system_schema`, etc.); pásale
  `include_system=True` para verlos.
- Cassandra requiere un balanceador de carga consciente del datacenter
  (`DCAwareRoundRobinPolicy`); por eso `RUVIC_CASSANDRA_LOCAL_DATACENTER`
  es obligatorio en modo directo, aunque el clúster tenga un solo
  datacenter. En modo Astra esto no aplica: el bundle ya trae la
  configuración de red del proxy seguro.
- El driver no soporta `JOIN`; las consultas deben respetar el modelo de
  particionamiento de cada tabla.
