#!/usr/bin/env python3
"""GigaScope Demo Seeder — готовит демо-данные одним прогоном.

Сценарий (синхронизирован с 3-минутным скриптом диктора):
  1. Проверка живости сервисов
  2. Сид логов (P95 spike на vm-db-node1)
  3. Анализ логов → гипотезы
  4. Инжест событий: 13 seed инцидентов (engine добавляет ещё 5 при generate → 18 всего)
  5. PROPAGATES_TO рёбра (каскадные связи в Neo4j)
  6. Пользовательские сигналы (волна жалоб на PaymentService)
  7. LLM-анализ vm-db-node1
  8. Engine generate (авто-генерация гипотез)
  9. Проверка risk-скоринга и Engine status

Целевое состояние (соответствует тексту диктора):
  - 9 гипотез (3 frequency + 6 cascade)
  - 18 инцидентов (7 critical + 9 warning + 2 info)
  - Database: risk ~46%, fail_4h ~35%, 5 инцидентов
  - PaymentService: risk ~18%, rising wave

Использование:
  python3 demo_seeder.py [--base-url http://localhost:8765]
"""

import sys
import json
import time
import argparse
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

API_BASE = f"{os.environ.get('OUROBOROS_API_URL', 'http://localhost:8765').rstrip('/')}/api/gigascope"
NEO4J_BOLT = os.environ.get("NEO4J_BOLT_URL", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD")

COLORS = {
    "GREEN": "\033[92m", "YELLOW": "\033[93m", "RED": "\033[91m",
    "CYAN": "\033[96m", "BOLD": "\033[1m", "END": "\033[0m",
}

def c(text, color):
    return f"{COLORS.get(color, '')}{text}{COLORS['END']}"

def _ts_minus_minutes(m):
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()

def api_call(method, path, body=None):
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}
    except Exception as e:
        return -1, {"error": str(e)}

def step(num, title):
    print(f"\n{c('-'*60, 'CYAN')}")
    print(f"{c(f'ШАГ {num}', 'BOLD')}: {c(title, 'CYAN')}")
    print(f"{c('-'*60, 'CYAN')}")

def check(label, ok, detail=""):
    status = c("OK", "GREEN") if ok else c("FAIL", "RED")
    print(f"  [{status}] {label}" + (f" - {detail}" if detail else ""))

# ── Инциденты для демо ──
# Database получает 5 инцидентов (для risk ~35% и frequency threshold ≥3)
DATABASE_INCIDENTS = [
    {"type": "vm_degraded", "service": "Database", "severity": "critical",
     "description": "vm-db-node1: CPU 95%, pool exhaustion, P95=3200ms"},
    {"type": "connection_pool_exhausted", "service": "Database", "severity": "critical",
     "description": "Connection pool exhausted (max=100, active=100)"},
    {"type": "replication_lag", "service": "Database", "severity": "warning",
     "description": "Replication lag: 2.3s on vm-db-node2"},
    {"type": "slow_query", "service": "Database", "severity": "warning",
     "description": "Slow query: SELECT * FROM transactions (2800ms)"},
    {"type": "disk_io_degraded", "service": "Database", "severity": "critical",
     "description": "Disk I/O degraded on vm-db-node1: iowait 45%"},
]

PAYMENT_INCIDENTS = [
    {"type": "service_degraded", "service": "PaymentService", "severity": "critical",
     "description": "PaymentService degraded - Database timeout. Rollback rate: 12%."},
    {"type": "timeout", "service": "PaymentService", "severity": "warning",
     "description": "Payment transaction timeout (3100ms)"},
]

ACCOUNT_INCIDENTS = [
    {"type": "service_degraded", "service": "AccountService", "severity": "warning",
     "description": "AccountService 502 errors - Database connection refused"},
    {"type": "auth_failure", "service": "AccountService", "severity": "warning",
     "description": "Account balance sync failure after payment"},
]

# Дополнительные инциденты для полных каскадных цепочек
EXTRA_INCIDENTS = [
    {"type": "service_degraded", "service": "TransactionService", "severity": "warning",
     "description": "TransactionService timeout - PaymentService dependency degraded"},
    {"type": "service_degraded", "service": "CRMGateway", "severity": "warning",
     "description": "CRMGateway 503 - AccountService dependency degraded"},
    {"type": "service_degraded", "service": "CRMGateway", "severity": "warning",
     "description": "CRMGateway slow response - AccountService cascade impact (additional)"},
    {"type": "info_event", "service": "AuthService", "severity": "info",
     "description": "AuthService performing within normal parameters - informational"},
]

# ── Каскадные связи (PROPAGATES_TO) ──
# Формат: (source_service, target_service) — инцидент распространяется
# Важно: связывает последние инциденты source→target по времени
CASCADE_CHAINS = [
    ("Database", "PaymentService"),
    ("Database", "AccountService"),
    ("Database", "TransactionService"),
    ("PaymentService", "TransactionService"),
    ("PaymentService", "CRMGateway"),
]

# ── Логи для vm-db-node1 (service=vm-db-node1 для LLM-анализа) ──
VM_LOGS = [
    {"source_id": "vm-db-node1", "source_type": "vm", "service": "vm-db-node1",
     "log_type": "response_time", "status_code": 200,
     "message": "PostgreSQL query latency spike", "response_time_ms": 3200,
     "timestamp": datetime.now(timezone.utc).isoformat()},
    {"source_id": "vm-db-node1", "source_type": "vm", "service": "vm-db-node1",
     "log_type": "error", "status_code": 503,
     "message": "connection pool exhausted (max=100, active=100)",
     "response_time_ms": 5000,
     "timestamp": datetime.now(timezone.utc).isoformat()},
    {"source_id": "vm-db-node1", "source_type": "vm", "service": "vm-db-node1",
     "log_type": "response_time", "status_code": 200,
     "message": "slow query: SELECT * FROM transactions",
     "response_time_ms": 2800,
     "timestamp": datetime.now(timezone.utc).isoformat()},
    {"source_id": "vm-db-node2", "source_type": "vm", "service": "vm-db-node1",
     "log_type": "response_time", "status_code": 200,
     "message": "replication lag: 2.3s", "response_time_ms": 2300,
     "timestamp": datetime.now(timezone.utc).isoformat()},
]

# Логи для PaymentService
PAYMENT_LOGS = [
    {"source_id": "payment-service", "source_type": "service", "service": "PaymentService",
     "log_type": "error", "status_code": 500,
     "message": "Database timeout: payment transaction rollback",
     "response_time_ms": 3100,
     "timestamp": datetime.now(timezone.utc).isoformat()},
    {"source_id": "payment-service", "source_type": "service", "service": "PaymentService",
     "log_type": "response_time", "status_code": 200,
     "message": "Payment processing slow (2500ms avg)",
     "response_time_ms": 2500,
     "timestamp": datetime.now(timezone.utc).isoformat()},
]


def create_propagates_to_edges():
    """Создаёт рёбра PROPAGATES_TO в Neo4j между последними инцидентами."""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_BOLT, auth=(NEO4J_USER, NEO4J_PASS))
    created_count = 0
    with driver.session() as session:
        for src_svc, tgt_svc in CASCADE_CHAINS:
            # Найти последние open инциденты source и target
            result = session.run(
                "MATCH (sa:Service {name: $src})-[:HAS_INCIDENT]->(ia:Incident {status: 'open'}), "
                "(sb:Service {name: $tgt})-[:HAS_INCIDENT]->(ib:Incident {status: 'open'}) "
                "WHERE ia.id <> ib.id "
                "WITH ia, ib ORDER BY ia.started_at DESC, ib.started_at DESC LIMIT 1 "
                "MERGE (ia)-[:PROPAGATES_TO]->(ib) "
                "RETURN ia.id AS src_id, ib.id AS tgt_id",
                src=src_svc, tgt=tgt_svc,
            ).single()
            if result:
                created_count += 1
                check(f"Cascade: {src_svc}→{tgt_svc}", True,
                      f"{result['src_id']}→{result['tgt_id']}")
            else:
                check(f"Cascade: {src_svc}→{tgt_svc}", False, "no incident pair found")
    driver.close()
    return created_count


def main():
    global API_BASE, NEO4J_BOLT, NEO4J_USER, NEO4J_PASS

    parser = argparse.ArgumentParser(description="GigaScope Demo Seeder")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OUROBOROS_API_URL", "http://localhost:8765"),
    )
    parser.add_argument("--neo4j-url", default=NEO4J_BOLT)
    parser.add_argument("--neo4j-user", default=NEO4J_USER)
    parser.add_argument("--neo4j-password", default=NEO4J_PASS)
    args = parser.parse_args()
    if not args.neo4j_password:
        parser.error("задайте --neo4j-password или переменную NEO4J_PASSWORD")

    API_BASE = f"{args.base_url.rstrip('/')}/api/gigascope"
    NEO4J_BOLT = args.neo4j_url
    NEO4J_USER = args.neo4j_user
    NEO4J_PASS = args.neo4j_password

    print(f"{c('GIGASCOPE DEMO SEEDER', 'BOLD')}")
    print(f"API: {API_BASE}")
    print(f"Neo4j: {NEO4J_BOLT}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{c('='*60, 'CYAN')}")

    # Step 1: Health check
    step(1, "Health check")
    code, engine = api_call("GET", "/engine/status")
    check("Engine API", code == 200,
          f"{engine.get('total_hypotheses', '?')} hypotheses, {engine.get('total_incidents', '?')} incidents")

    code, graph = api_call("GET", "/graph")
    check("Graph API", code == 200,
          f"{len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")

    # Step 2: Seed logs
    step(2, "Seed demo logs (P95/P99 percentiles)")

    code, seed_result = api_call("POST", "/logs/seed", {})
    check("Logs seed (built-in)", code == 200,
          f"seeded={seed_result.get('seeded', '?')} entries")

    for log in VM_LOGS + PAYMENT_LOGS:
        code, result = api_call("POST", "/logs/ingest", log)
        check(f"Ingest {log['source_id']} ({log['log_type']})", code == 200)

    # Step 3: Analyze logs
    step(3, "Run log analysis (anomaly detection)")
    code, analysis = api_call("POST", "/logs/analyze", {})
    check("Log analysis", code == 200,
          f"anomalies={len(analysis.get('anomalies', []))}, "
          f"hypotheses={len(analysis.get('hypotheses', []))}")

    if analysis.get("anomalies"):
        print(f"\n  {c('Anomalies found:', 'YELLOW')}")
        for a in analysis.get("anomalies", [])[:5]:
            print(f"    - {a.get('anomaly_type', '?')} | {a.get('service', '?')} | P95={a.get('p95_ms', '?')}ms")

    if analysis.get("hypotheses"):
        print(f"\n  {c('Log hypotheses:', 'YELLOW')}")
        for h in analysis.get("hypotheses", [])[:3]:
            text = h.get('text', '?')
            if isinstance(text, str): text = text[:80]
            print(f"    - [{h.get('id', '?')}] {text}...")

    # Step 4: Ingest events (5 Database + 2 Payment + 2 Account + 2 extra + 1 info + 1 extra = 13 incidents)
    step(4, "Ingest events (Database x5, Payment x2, Account x2, Extra x3, Info x1 = 13 total)")

    all_incidents = DATABASE_INCIDENTS + PAYMENT_INCIDENTS + ACCOUNT_INCIDENTS + EXTRA_INCIDENTS
    incident_ids = {}
    for ev in all_incidents:
        code, result = api_call("POST", "/events", ev)
        inc_id = result.get('id', '?')
        check(f"Event: {ev['service']} ({ev['severity']})", code == 201,
              f"id={inc_id}")
        if code == 201:
            incident_ids.setdefault(ev['service'], []).append(inc_id)

    # Step 5: Create PROPAGATES_TO edges (cascade links in Neo4j)
    step(5, "Create cascade edges (PROPAGATES_TO) in Neo4j")
    try:
        edge_count = create_propagates_to_edges()
        check("Cascade edges", edge_count > 0, f"{edge_count} edges created")
    except Exception as e:
        check("Cascade edges", False, f"Neo4j error: {e}")

    # Step 6: User signals (wave of complaints)
    step(6, "User signals (rising wave on PaymentService)")

    user_requests = [
        {"service": "PaymentService", "description": "Cannot pay by card - timeout error",
         "source": "user", "severity": "critical", "created_at": _ts_minus_minutes(20)},
        {"service": "PaymentService", "description": "Payment stuck for 3 minutes then rollback",
         "source": "user", "severity": "warning", "created_at": _ts_minus_minutes(15)},
        {"service": "PaymentService", "description": "Cannot pay for services - service unavailable",
         "source": "user", "severity": "critical", "created_at": _ts_minus_minutes(10)},
        {"service": "PaymentService", "description": "Mass complaints about payments in call center",
         "source": "monitoring", "severity": "critical", "created_at": _ts_minus_minutes(10)},
        {"service": "PaymentService", "description": "Payment system completely down - all transactions failing",
         "source": "monitoring", "severity": "critical", "created_at": _ts_minus_minutes(5)},
        {"service": "PaymentService", "description": "Multiple users reporting payment failures",
         "source": "user", "severity": "critical"},
        {"service": "AccountService", "description": "Cannot login to personal account - 502",
         "source": "user", "severity": "warning", "created_at": _ts_minus_minutes(12)},
        {"service": "AccountService", "description": "Balance not updating after payment",
         "source": "user", "severity": "info", "created_at": _ts_minus_minutes(7)},
        {"service": "AccountService", "description": "Login page returns 502 for all users",
         "source": "monitoring", "severity": "critical"},
    ]

    for ur in user_requests:
        code, result = api_call("POST", "/user-requests", ur)
        wave = result.get("wave_status", {})
        hyp = result.get("hypothesis_result", {})
        check(f"User request: {ur['service']}", code == 200,
              f"wave={wave.get('trend', '?')}, hyp={hyp.get('action', '?')}")

    # Step 7: LLM analysis of vm-db-node1
    step(7, "LLM analysis of vm-db-node1")

    code, analyzed = api_call("GET", "/logs/llm-analyzed")
    already = set(analyzed.get("analyzed_services", []))
    print(f"  Already analyzed by LLM: {already or 'empty'}")

    llm_target = "vm-db-node1"
    if llm_target not in already:
        code, llm_result = api_call("POST", "/logs/llm-analyze", {
            "service": llm_target, "model": "openai/gpt-5.2"})
        if code == 200:
            check(f"LLM analysis: {llm_target}", True,
                  f"confidence={llm_result.get('confidence', '?')}")
            print(f"\n  {c('LLM diagnosis:', 'YELLOW')}")
            for field in ("root_cause", "impact", "recommended_action"):
                val = llm_result.get(field, '?')
                if isinstance(val, str): val = val[:100]
                print(f"    {field}: {val}")
        else:
            check(f"LLM analysis: {llm_target}", False,
                  f"code={code}, err={str(llm_result.get('error', '?'))[:80]}")
    else:
        check(f"LLM analysis: {llm_target}", True, "already analyzed")

    # Step 8: Engine generate (auto-generates hypotheses from patterns + cascades)
    step(8, "Engine: generate hypotheses (patterns + cascades + frequency)")
    code, gen_result = api_call("POST", "/engine/generate", {})
    check("Engine generate", code == 200,
          f"created={len(gen_result.get('created', []))}, "
          f"existing={len(gen_result.get('existing', []))}")

    if gen_result.get("created"):
        print(f"\n  {c('Created hypotheses:', 'YELLOW')}")
        for h in gen_result["created"][:5]:
            text = h.get('text', '?')
            if isinstance(text, str): text = text[:80]
            print(f"    - [{h.get('id', '?')}] {text} (conf={h.get('confidence', '?')})")

    # Step 9: Final verification
    step(9, "Final state verification")

    code, engine_final = api_call("GET", "/engine/status")
    hyp_count = engine_final.get('total_hypotheses', 0)
    inc_count = engine_final.get('total_incidents', 0)
    check("Engine status", code == 200,
          f"hypotheses={hyp_count}, incidents={inc_count}")

    code, preds_final = api_call("GET", "/predictions")
    if code == 200:
        print(f"\n  {c('Risk Scores:', 'YELLOW')}")
        for svc in preds_final.get("services", []):
            risk_pct = svc.get("risk_score", 0) * 100
            fail_pct = svc.get("failure_probability_4h", 0) * 100
            icon = "RED" if risk_pct > 30 else ("YELLOW" if risk_pct > 15 else "GREEN")
            print(f"    [{c(icon, icon)}] {svc['name']}: risk={risk_pct:.1f}%, "
                  f"fail_4h={fail_pct:.1f}%, incidents={svc.get('open_incidents', 0)}")

    code, wave_all = api_call("GET", "/user-requests/wave-status")
    if code == 200:
        statuses = wave_all.get("statuses", [])
        if statuses:
            print(f"\n  {c('Wave Status:', 'YELLOW')}")
            for w in statuses:
                print(f"    - {w.get('service', '?')}: trend={w.get('trend', '?')}")
        else:
            print(f"\n  {c('Wave Status:', 'YELLOW')} - insufficient data")

    print(f"\n{c('='*60, 'GREEN')}")
    print(f"{c('DEMO DATA READY', 'BOLD')}")
    print(f"{c('='*60, 'GREEN')}")
    print(f"\nExpected state (matching 3-min script):")
    print(f"  - Database: risk ~46%, 5 incidents, cascades to Payment/Account/Transaction/CRM")
    print(f"  - PaymentService: risk ~18%, 2 incidents, rising wave")
    print(f"  - Hypotheses: 9 (3 frequency + 6 cascade)")
    print(f"  - Incidents: 18 (7 critical + 9 warning + 2 info)")
    print(f"  - Cascade edges: 5 PROPAGATES_TO in Neo4j")
    print(f"  - VM logs: vm-db-node1 P95=3200ms, LLM diagnosis ready")
    print(f"  - Fail_4h Database: ~35%")
    print(f"\nSPA: http://localhost:8099")
    print(f"API: {API_BASE}")


if __name__ == "__main__":
    main()
