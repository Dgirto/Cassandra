---
name: cassandra
description: >
  Usa la librería ruvic_cassandra_connector para consultar clústeres Apache
  Cassandra en modo solo lectura - listar keyspaces y sus tablas
  (list_keyspaces_and_tables), leer filas de una tabla con límite
  (read_rows) y ejecutar una sentencia CQL de solo lectura (execute_cql).
  Úsala cuando el usuario pida consultar, explorar o analizar datos en
  Cassandra.
triggers:
- cassandra
- apache cassandra
- cql
- keyspace de cassandra
---

# Conector Cassandra (ruvic_cassandra_connector)

Librería Python de solo lectura para Apache Cassandra. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/Cassandra.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `cassandra` está configurado. Hay dos modos posibles según cómo el usuario configuró el conector — el código nunca necesita saber cuál es, `CassandraClient()` detecta el modo solo:

**Modo directo** (clúster self-hosted):

| Variable | Contenido |
|----------|-----------|
| `RUVIC_CASSANDRA_HOSTS` | Nodos de contacto separados por coma |
| `RUVIC_CASSANDRA_PORT` | Puerto (default 9042) |
| `RUVIC_CASSANDRA_USERNAME` | Usuario |
| `RUVIC_CASSANDRA_PASSWORD` | Contraseña |
| `RUVIC_CASSANDRA_LOCAL_DATACENTER` | Datacenter local requerido por el driver |

**Modo Astra** (DataStax Astra DB):

| Variable | Contenido |
|----------|-----------|
| `RUVIC_CASSANDRA_SECURE_CONNECT_BUNDLE_B64` | Secure Connect Bundle en base64 |
| `RUVIC_CASSANDRA_TOKEN` | Application Token de Astra |

Común a ambos: `RUVIC_CASSANDRA_CONNECT_TIMEOUT` (opcional, timeout en segundos).

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

## Solo se permiten sentencias SELECT

`execute_cql` rechaza cualquier sentencia que no empiece con `SELECT` (INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, TRUNCATE), sin importar el rol otorgado al usuario.

## Conexión (siempre igual)

```python
from ruvic_cassandra_connector import CassandraClient

client = CassandraClient()  # lee RUVIC_CASSANDRA_* del entorno automáticamente
```

## Capacidad 1 — Listar keyspaces y tablas

```python
keyspaces = client.list_keyspaces_and_tables()
for keyspace, tables in keyspaces.items():
    print(f"{keyspace}: {tables}")
```

## Capacidad 2 — Leer filas de una tabla

```python
rows = client.read_rows("ventas", "pedidos", limit=50)
for row in rows:
    print(row)
```

## Capacidad 3 — Ejecutar una sentencia CQL de lectura

```python
rows = client.execute_cql(
    "SELECT id, cliente, monto FROM pedidos WHERE cliente = 'ACME' LIMIT 100",
    keyspace="ventas",
)
```

Usa siempre un `LIMIT` razonable en consultas exploratorias para no traer datasets enormes.

## Manejo de errores

```python
from ruvic_cassandra_connector import (
    CassandraAuthError, CassandraDataError, CassandraNetworkError,
)

try:
    rows = client.read_rows("ventas", "pedidos", limit=10)
except CassandraAuthError:
    print("Credenciales inválidas o sin permiso suficiente")
except CassandraNetworkError:
    print("No se pudo alcanzar el clúster — reintenta en unos segundos")
except CassandraDataError as e:
    print(f"Error de datos: {e}")  # ej. la tabla no existe o la consulta es inválida
```

## Comportamiento conversacional

### Cuándo pedir aclaración (y cuándo NO)

Pide aclaración únicamente cuando la consulta requiere filtrar por una entidad
específica (ej. un cliente), el usuario no la nombró ni dio nada que la
identifique, y existe más de una posible. En cualquier otro caso, responde
directo — nunca preguntes "de más".

| Situación | ¿Preguntar? |
|---|---|
| El usuario pide una agregación, ranking o promedio ("¿cuál cliente compró más?", "total del mes") | No — el sistema lo calcula solo, sin necesitar que el usuario elija nada |
| El usuario pide datos de "el cliente" sin decir cuál, y hay varios posibles | Sí — pregunta cuál, mostrando las opciones disponibles si las tienes a mano |
| El usuario nombra la entidad, exacta o aproximada (ej. "empresa cinco" en vez de "Empresa 5") | No — resuélvelo por coincidencia razonable, no pidas que lo repita exacto |
| El usuario nombra una entidad que no existe en los datos | No es ambigüedad — informa que no existe y, si es útil, muestra qué valores sí hay |

### Sugerencias de seguimiento

Después de responder, ofrece una sugerencia de seguimiento solo si deja algo
útil sin resolver — no la agregues en cada respuesta, se vuelve ruido. Ejemplo:
si mostraste el total de un cliente, puede tener sentido ofrecer comparar
contra el promedio general; si ya mostraste un ranking completo, no sugieras
nada más, la respuesta ya está completa.

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_CASSANDRA_*` (el constructor de `CassandraClient` ya lo hace).
2. Nunca imprimas `RUVIC_CASSANDRA_PASSWORD` ni `RUVIC_CASSANDRA_TOKEN` en logs ni en la salida.
3. La librería es de SOLO LECTURA: no intentes construir CQL con INSERT/UPDATE/DELETE, el conector los rechaza igual.
4. Usa `limit` razonable en `read_rows` (default 100, máximo 1000) para no traer resultados masivos a memoria.
5. Cassandra no soporta `JOIN` ni consultas ad-hoc por columnas sin índice secundario o clave de partición — si una consulta falla, revisa el modelo de datos de la tabla antes de reintentar.
