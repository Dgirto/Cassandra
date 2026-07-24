"""Validación local del conector cassandra: ejercita las 3 capacidades.

Uso:
    python validate_local.py

Requiere las variables RUVIC_CASSANDRA_* exportadas en el entorno, y un
keyspace "ventas" con una tabla "pedidos" con al menos una fila.
"""

from ruvic_cassandra_connector import CassandraClient, setup_logging

setup_logging("INFO")
client = CassandraClient()

print("== 1. Keyspaces y tablas ==")
for keyspace, tables in client.list_keyspaces_and_tables().items():
    print(f"  {keyspace}: {tables}")

print("== 2. Leer filas (ventas.pedidos, limit=10) ==")
rows = client.read_rows("ventas", "pedidos", limit=10)
for row in rows:
    print(f"  {row}")

print("== 3. Ejecutar CQL de lectura ==")
rows = client.execute_cql("SELECT * FROM pedidos LIMIT 5", keyspace="ventas")
print(f"  {len(rows)} filas")

print("\nTodo OK: list_keyspaces_and_tables, read_rows y execute_cql funcionan.")
