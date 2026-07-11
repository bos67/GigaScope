"""GigaScope Demo Scenario — симуляция каскадного отказа PaymentService.

Запуск: python demo_scenario.py
Сценарий:

1. PaymentService начинает медленно отвечать (latency spike)
2. Через 30с — timeout, PaymentService падает
3. Через 60с — TransactionService тоже падает (каскад)
4. PaymentService восстанавливается
5. Анализ — Ouroboros travers'ит граф и выдаёт гипотезу
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx


OUROBOROS_API = os.environ.get("OUROBOROS_API_URL", "http://localhost:8080")
EVENT_URL = f"{OUROBOROS_API}/api/gigascope/events"
HYPOTHESES_URL = f"{OUROBOROS_API}/api/gigascope/hypotheses"
GRAPH_URL = f"{OUROBOROS_API}/api/gigascope/graph"


def send_event(event_type: str, service: str, severity: str, description: str):
    """Send an event to GigaScope API."""
    payload = {
        "type": event_type,
        "service": service,
        "severity": severity,
        "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = httpx.post(EVENT_URL, json=payload, timeout=10.0)
        data = resp.json()
        print(f"  [{resp.status_code}] {event_type.upper()} | {service} | {severity}")
        print(f"    → Incident ID: {data.get('id', '?')}")
        return data
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return None


def print_graph_status():
    """Print current graph status."""
    try:
        resp = httpx.get(GRAPH_URL, timeout=10.0)
        data = resp.json()
        nodes = data.get("nodes", [])
        critical = [n for n in nodes if n["status"] in ("critical", "down")]
        warning = [n for n in nodes if n["status"] == "warning"]
        healthy = [n for n in nodes if n["status"] == "healthy"]
        print(f"\n📊 GRAPH STATUS: {len(healthy)} healthy, "
              f"{len(warning)} warning, {len(critical)} critical")
        for n in critical:
            print(f"   🔴 {n['id']} — CRITICAL")
        for n in warning:
            print(f"   🟡 {n['id']} — WARNING")
        return data
    except Exception as e:
        print(f"  ❌ GRAPH ERROR: {e}")
        return None


def list_hypotheses():
    """List current hypotheses."""
    try:
        resp = httpx.get(HYPOTHESES_URL, timeout=10.0)
        data = resp.json()
        hyps = data.get("hypotheses", [])
        print(f"\n🧪 HYPOTHESES: {len(hyps)} active")
        for h in hyps:
            confidence_pct = h.get("confidence", 0) * 100
            status_icon = "✅" if h.get("status") == "confirmed" else "🔬"
            print(f"   {status_icon} {h['id']} ({confidence_pct:.0f}%): {h['text'][:80]}...")
        return data
    except Exception as e:
        print(f"  ❌ HYPOTHESES ERROR: {e}")
        return None


def run_demo():
    """Run the complete demo scenario."""
    print("=" * 60)
    print("  🚀 GIGASCOPE DEMO — CASCADING FAILURE")
    print("  Банковский стенд: PaymentService → TransactionService")
    print("=" * 60)

    # Step 0: Initial state
    print("\n📌 STEP 0: Initial State — все сервисы здоровы")
    print_graph_status()
    list_hypotheses()
    time.sleep(2)

    # Step 1: Latency spike
    print("\n" + "=" * 60)
    print("📌 STEP 1: Latency Spike — PaymentService начинает тормозить")
    print("=" * 60)
    send_event("latency", "PaymentService", "warning",
               "PaymentService latency spike +350% — connection pool nearing limit")
    print_graph_status()
    time.sleep(3)

    # Step 2: Timeout — PaymentService падает
    print("\n" + "=" * 60)
    print("📌 STEP 2: Timeout — PaymentService connection pool exhausted")
    print("=" * 60)
    send_event("timeout", "PaymentService", "critical",
               "PaymentService connection pool exhausted — all requests timing out")
    print_graph_status()
    time.sleep(3)

    # Step 3: Cascading failure — TransactionService тоже падает
    print("\n" + "=" * 60)
    print("📌 STEP 3: Cascading Failure — TransactionService падает следом")
    print("=" * 60)
    send_event("timeout", "TransactionService", "critical",
               "TransactionService cannot process payments — upstream PaymentService is down")
    # Database gets slow too
    send_event("latency", "Database", "warning",
               "Database connection pool under pressure — query latency +200%")
    print_graph_status()
    time.sleep(3)

    # Step 4: Recovery starts
    print("\n" + "=" * 60)
    print("📌 STEP 4: Recovery — PaymentService восстанавливается")
    print("=" * 60)
    send_event("recovery", "PaymentService", "info",
               "PaymentService recovered — connection pool restored, requests flowing")
    send_event("recovery", "TransactionService", "info",
               "TransactionService recovered — processing queue draining")
    print_graph_status()
    time.sleep(2)

    # Step 5: Analysis — проверяем гипотезы
    print("\n" + "=" * 60)
    print("📌 STEP 5: Ouroboros Analysis — что показывает Hypothesis Registry?")
    print("=" * 60)
    list_hypotheses()

    # Check the top hypothesis traversal
    print("\n🔍 Traversal: PaymentService incidents")
    try:
        # First check if any incidents were created
        incidents_resp = httpx.get(
            f"{OUROBOROS_API}/api/gigascope/incidents",
            timeout=10.0,
        )
        incidents = incidents_resp.json().get("incidents", [])
        print(f"\n📋 Recent incidents: {len(incidents)} total")
        if incidents:
            # Get the latest open incident
            latest = incidents[0]
            print(f"   Latest: {latest['id']} — {latest['description'][:60]}")

            # Traverse it
            trav_resp = httpx.get(
                f"{OUROBOROS_API}/api/gigascope/incidents/{latest['id']}/traverse",
                timeout=10.0,
            )
            if trav_resp.status_code == 200:
                trav_data = trav_resp.json()
                print(f"\n🧠 Analysis: {trav_data.get('analysis', 'No analysis')}")

                hyps = trav_data.get("related_hypotheses", [])
                if hyps:
                    print(f"\n🔬 Related hypotheses ({len(hyps)}):")
                    for h in hyps:
                        print(f"   • {h['text'][:100]}")
                        print(f"     Confidence: {h.get('confidence', 0)*100:.0f}%")
    except Exception as e:
        print(f"  ❌ TRAVERSAL ERROR: {e}")

    print("\n" + "=" * 60)
    print("  ✅ DEMO COMPLETE")
    print("  Открой GigaScope SPA на http://localhost:8099")
    print("  чтобы увидеть граф в 3D")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
