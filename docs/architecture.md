# GigaScope Architecture (MVP)

## Overview

GigaScope — система мониторинга и анализа инцидентов банковской инфраструктуры.
MVP строится для демонстрации концепции заказчику: как Ouroboros (когнитивный слой)
обнаруживает, анализирует и объясняет инциденты на основе графа зависимостей.

## Architecture Decision: Variant C (Hybrid)

- **GigaScope API** — модуль внутри Ouroboros (`ouroboros/gateway/gigascope.py`) на порту 8099
- **GigaScope Frontend** — отдельное SPA (Three.js 3D-граф) на порту 8099
- **Neo4j** — единый граф (инциденты, инфраструктура, гипотезы)
- **Analysis Engine** — инструменты Ouroboros (traversal, hypothesis registry)

## Deployment (MVP: одна VM Cloud.ru)

```
┌──────────────────────────────────────────────────┐
│                Одна VM (Cloud.ru)                  │
│  ┌────────────────────────────────────────────┐    │
│  │         Ouroboros Process                    │    │
│  │  ┌──────────┐   ┌──────────────────┐       │    │
│  │  │ Chat UI  │   │ GigaScope API    │       │    │
│  │  │ (:8080)  │   │ (/api/gigascope) │       │    │
│  │  └──────────┘   └────────┬─────────┘       │    │
│  │  ┌───────────────────────┴────────────┐    │    │
│  │  │   Analysis Engine                   │    │    │
│  │  │   - Neo4j traversal driver          │    │    │
│  │  │   - Hypothesis Registry CRUD        │    │    │
│  │  │   - Confidence scoring              │    │    │
│  │  └────────────────────────────────────┘    │    │
│  └────────────────────────────────────────────┘    │
│  ┌──────────────────────┐    ┌──────────────────┐  │
│  │ Neo4j (Docker)       │    │ GigaScope SPA    │  │
│  │ bolt://172.17.0.2:7687│    │ Three.js, :8099  │  │
│  └──────────────────────┘    └──────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## Service Topology (Банковский стенд)

| Service | Type | Sync | Async | Depends On |
|---------|------|------|-------|------------|
| APIGateway | API Gateway | REST | — | — |
| AuthService | Auth | REST | — | Database |
| PaymentService | Core Banking | gRPC | Kafka (events) | AuthService, Database |
| AccountService | Core Banking | REST | Kafka | Database |
| TransactionService | Core Banking | — | Kafka (consumer) | PaymentService |
| NotificationService | Infrastructure | — | Kafka (consumer) | — |
| Database | Storage | Bolt | — | — |
| Kafka | Messaging | — | — | — |

## Sync vs Async Communication

### Synchronous (REST/gRPC)
- APIGateway → AuthService (REST: `/auth/validate`)
- APIGateway → PaymentService (gRPC: `ProcessPayment`)
- APIGateway → AccountService (REST: `/account/balance`)
- PaymentService → AuthService (gRPC: `ValidateToken`)
- PaymentService → Database (Bolt: Neo4j queries)
- AccountService → Database (Bolt)

### Asynchronous (Kafka topics)
- `payment.events` — PaymentService → TransactionService
- `account.events` — AccountService → NotificationService
- `system.health` — heartbeat от всех сервисов
- `incidents.alerts` — канал оповещений

## Data Flow

```
Event Producer → Kafka/In-process Queue → Processing → Neo4j Graph
                                                          ↓
                                             Ouroboros Analysis Engine
                                              (traversal + hypotheses)
                                                          ↓
                                          GigaScope API → GigaScope SPA
```

## Hypothesis Registry (Neo4j Schema)

```cypher
(:Hypothesis {
    id: string,
    text: string,
    confidence: float,        // 0.0 - 1.0
    status: string,           // active | confirmed | refuted | stale
    created_by: string,       // "human" | "ouroboros" | "auto"
    created_at: datetime,
    last_checked_at: datetime,
    evidence_count: int,
    tags: [string]
})

(:Evidence {
    id: string,
    text: string,
    weight: float,            // 0.0 - 1.0
    source_type: string,      // "incident" | "pattern" | "human_input"
    source_ref: string,
    supports_hypothesis: bool,
    created_at: datetime
})

(:Incident {
    id: string,
    type: string,
    severity: string,
    status: string,
    started_at: datetime,
    resolved_at: datetime?,
    description: string
})

(:Service {
    id: string,
    name: string,
    type: string,
    status: string,
    metadata: map
})

// Relationships
(:Hypothesis)-[:HAS_EVIDENCE]->(:Evidence)
(:Hypothesis)-[:RELATES_TO]->(:Incident)
(:Service)-[:DEPENDS_ON]->(:Service)     // sync dependency
(:Service)-[:SUBSCRIBES_TO]->(:Service)  // async (Kafka topic)
(:Service)-[:HAS_INCIDENT]->(:Incident)
(:Incident)-[:CAUSED_BY]->(:Symptom)
(:Incident)-[:PROPAGATES_TO]->(:Incident)
```

## API Endpoints (GigaScope API)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/gigascope/services` | Все сервисы и их статус |
| GET | `/api/gigascope/services/:id` | Детали сервиса |
| GET | `/api/gigascope/incidents` | Все инциденты |
| GET | `/api/gigascope/incidents/:id/traverse` | Traversal цепочки |
| GET | `/api/gigascope/hypotheses` | Все гипотезы |
| POST | `/api/gigascope/hypotheses` | Создать гипотезу |
| PUT | `/api/gigascope/hypotheses/:id/verify` | Проверить гипотезу |
| GET | `/api/gigascope/graph` | Полный граф для SPA |
| POST | `/api/gigascope/events` | Входящее событие |
| WS | `/api/gigascope/ws` | Real-time обновления |

## Phased Evolution

### Phase 0 (Week 1 — MVP Demo)
- Neo4j: инфраструктурная карта + 5-7 смоделированных инцидентов
- GigaScope API: базовые endpoints (services, incidents, graph)
- GigaScope SPA: 3D-граф с подсветкой проблем
- Event Producer: симуляция падения PaymentService
- Analysis Engine: traversal от инцидента к корню
- Hypothesis Registry: создание/чтение гипотез

### Phase 1 (Post-MVP)
- Hypothesis confidence scoring на основе частоты паттернов
- Проактивный polling графа
- Автоматическое создание гипотез при обнаружении аномалий

### Phase 2 (Production)
- Real-time WebSocket стриминг
- Предиктивный анализ
- Kafka вместо in-process очереди
- Разделение на микросервисы
