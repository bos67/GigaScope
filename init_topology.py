#!/usr/bin/env python3
"""GigaScope Topology Initializer — создаёт скелет графа в пустой Neo4j.

Создаёт:
  - 6 Service nodes (Database, PaymentService, TransactionService,
    AuthService, AccountService, CRMGateway)
  - 6 DEPENDS_ON связей

НЕ создаёт:
  - Incidents, Hypotheses, Evidence (это делает demo_seeder.py)
  - VM, disk arrays, cluster nodes (это синтезирует _build_two_layer_graph())
  - User signals (in-memory, делает demo_seeder.py)

Использование:
  python3 init_topology.py [--bolt-url bolt://localhost:7687] [--user neo4j] [--password PASSWORD]

Аргументы по умолчанию читаются из NEO4J_BOLT_URL, NEO4J_USER и
NEO4J_PASSWORD. Пароль обязателен: секретного значения по умолчанию нет.

Запускать после пересоздания Neo4j (чистая база), ДО demo_seeder.py.
"""

import argparse
import os

from neo4j import GraphDatabase

# ── Топология сервисов ──
# Формат: (name, type, status, metadata)
# status = "healthy" — для чистого старта (demo_seeder меняет статусы через события)
SERVICES = [
    ("Database",          "database",     "healthy",   '{"cpu": "32", "ram": "256", "role": "primary-db"}'),
    ("PaymentService",    "application",  "healthy",   '{"cpu": "4", "ram": "16", "endpoint": "/api/payments"}'),
    ("TransactionService","application",  "healthy",   '{"cpu": "4", "ram": "16", "endpoint": "/api/transactions"}'),
    ("AuthService",       "application",  "healthy",   '{"cpu": "2", "ram": "8", "endpoint": "/api/auth"}'),
    ("AccountService",    "application",  "healthy",   '{"cpu": "4", "ram": "16", "endpoint": "/api/accounts"}'),
    ("CRMGateway",        "gateway",      "healthy",   '{"cpu": "2", "ram": "8", "endpoint": "/api/crm"}'),
]

# ── Зависимости (DEPENDS_ON) ──
# Формат: (source, target) — source зависит от target
DEPENDENCIES = [
    ("PaymentService",     "Database"),
    ("TransactionService", "PaymentService"),
    ("AuthService",        "Database"),
    ("AccountService",     "Database"),
    ("CRMGateway",         "Database"),
    ("CRMGateway",         "AccountService"),
]


def main():
    parser = argparse.ArgumentParser(description="GigaScope Topology Initializer")
    parser.add_argument("--bolt-url", default=os.environ.get("NEO4J_BOLT_URL", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD"))
    args = parser.parse_args()
    if not args.password:
        parser.error("задайте --password или переменную NEO4J_PASSWORD")

    print("=" * 60)
    print("GIGASCOPE TOPOLOGY INITIALIZER")
    print(f"  Bolt:   {args.bolt_url}")
    print(f"  User:   {args.user}")
    print("=" * 60)

    driver = GraphDatabase.driver(args.bolt_url, auth=(args.user, args.password))

    with driver.session() as session:
        # Проверка — есть ли уже Service nodes?
        result = session.run("MATCH (s:Service) RETURN count(s) AS count")
        existing = result.single()["count"]
        if existing > 0:
            print(f"\n⚠ В базе уже {existing} Service nodes. Очищаю...")
            session.run("MATCH (n) DETACH DELETE n")
            print("  База очищена.")

        # Создаём сервисы
        print(f"\nСоздание Service nodes ({len(SERVICES)} узлов)...")
        for name, svc_type, status, metadata in SERVICES:
            session.run(
                "CREATE (s:Service {name: $name, type: $type, status: $status, metadata: $metadata})",
                name=name, type=svc_type, status=status, metadata=metadata,
            )
            print(f"  ✅ {name} ({svc_type})")

        # Создаём зависимости
        print(f"\nСоздание DEPENDS_ON связей ({len(DEPENDENCIES)} рёбер)...")
        for source, target in DEPENDENCIES:
            session.run(
                "MATCH (a:Service {name: $src}), (b:Service {name: $tgt}) "
                "CREATE (a)-[:DEPENDS_ON]->(b)",
                src=source, tgt=target,
            )
            print(f"  ✅ {source} -> {target}")

        # Проверка
        result = session.run("MATCH (s:Service) RETURN count(s) AS count")
        count = result.single()["count"]
        print(f"\n{'=' * 60}")
        print(f"✅ ГОТОВО: {count} Service nodes создано")
        print(f"{'=' * 60}")
        print(f"\nСледующий шаг:")
        print(f"  python3 demo_seeder.py")
        print(f"\nПроверка:")
        print(f"  curl http://localhost:8765/api/gigascope/graph | python3 -m json.tool")

    driver.close()


if __name__ == "__main__":
    main()
