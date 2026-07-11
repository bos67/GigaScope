// GigaScope — Neo4j Schema Initialization
// Запуск: cat 01_init_schema.cypher | docker exec -i gigascope-neo4j cypher-shell -u neo4j -p gigascope123

// === 1. Constraints ===
CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT incident_id IF NOT EXISTS FOR (i:Incident) REQUIRE i.id IS UNIQUE;
CREATE CONSTRAINT hypothesis_id IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.id IS UNIQUE;

// === 2. Banking Services ===
MERGE (gw:Service {name: 'APIGateway'}) SET gw.type = 'API Gateway', gw.status = 'healthy', gw.metadata = '{"port":8080,"version":"2.1.0"}';
MERGE (auth:Service {name: 'AuthService'}) SET auth.type = 'Auth', auth.status = 'healthy', auth.metadata = '{"port":8081,"version":"1.5.2"}';
MERGE (pmt:Service {name: 'PaymentService'}) SET pmt.type = 'Core Banking', pmt.status = 'healthy', pmt.metadata = '{"port":8082,"version":"3.0.1"}';
MERGE (acc:Service {name: 'AccountService'}) SET acc.type = 'Core Banking', acc.status = 'healthy', acc.metadata = '{"port":8083,"version":"2.2.0"}';
MERGE (txn:Service {name: 'TransactionService'}) SET txn.type = 'Core Banking', txn.status = 'healthy', txn.metadata = '{"port":8084,"version":"1.8.0"}';
MERGE (notif:Service {name: 'NotificationService'}) SET notif.type = 'Infrastructure', notif.status = 'healthy', notif.metadata = '{"port":8085,"version":"1.2.0"}';
MERGE (db:Service {name: 'Database'}) SET db.type = 'Storage', db.status = 'healthy', db.metadata = '{"type":"PostgreSQL","version":"16.2"}';
MERGE (kafka:Service {name: 'Kafka'}) SET kafka.type = 'Messaging', kafka.status = 'healthy', kafka.metadata = '{"version":"3.6.0","topics":4}';

// === 3. Sync Dependencies (REST/gRPC) ===
MATCH (gw:Service {name: 'APIGateway'}), (auth:Service {name: 'AuthService'}) MERGE (gw)-[:DEPENDS_ON]->(auth);
MATCH (gw:Service {name: 'APIGateway'}), (pmt:Service {name: 'PaymentService'}) MERGE (gw)-[:DEPENDS_ON]->(pmt);
MATCH (gw:Service {name: 'APIGateway'}), (acc:Service {name: 'AccountService'}) MERGE (gw)-[:DEPENDS_ON]->(acc);
MATCH (pmt:Service {name: 'PaymentService'}), (auth:Service {name: 'AuthService'}) MERGE (pmt)-[:DEPENDS_ON]->(auth);
MATCH (pmt:Service {name: 'PaymentService'}), (db:Service {name: 'Database'}) MERGE (pmt)-[:DEPENDS_ON]->(db);
MATCH (acc:Service {name: 'AccountService'}), (db:Service {name: 'Database'}) MERGE (acc)-[:DEPENDS_ON]->(db);
MATCH (txn:Service {name: 'TransactionService'}), (db:Service {name: 'Database'}) MERGE (txn)-[:DEPENDS_ON]->(db);

// === 4. Async Dependencies (Kafka) ===
MATCH (pmt:Service {name: 'PaymentService'}), (txn:Service {name: 'TransactionService'}) MERGE (pmt)-[:SUBSCRIBES_TO]->(txn);
MATCH (acc:Service {name: 'AccountService'}), (notif:Service {name: 'NotificationService'}) MERGE (acc)-[:SUBSCRIBES_TO]->(notif);

// === 5. Historical Incidents ===
MATCH (pmt:Service {name: 'PaymentService'})
MERGE (i1:Incident {id: 'INC-001'}) SET i1.type = 'timeout', i1.severity = 'critical', i1.status = 'resolved',
    i1.started_at = '2026-06-05T19:30:00', i1.resolved_at = '2026-06-05T20:15:00',
    i1.description = 'PaymentService timeout - connection pool exhausted'
MERGE (pmt)-[:HAS_INCIDENT]->(i1);

MATCH (pmt:Service {name: 'PaymentService'})
MERGE (i2:Incident {id: 'INC-002'}) SET i2.type = 'latency', i2.severity = 'warning', i2.status = 'resolved',
    i2.started_at = '2026-06-12T18:45:00', i2.resolved_at = '2026-06-12T19:00:00',
    i2.description = 'PaymentService latency spike +400%'
MERGE (pmt)-[:HAS_INCIDENT]->(i2);

MATCH (pmt:Service {name: 'PaymentService'})
MERGE (i3:Incident {id: 'INC-003'}) SET i3.type = 'outage', i3.severity = 'critical', i3.status = 'resolved',
    i3.started_at = '2026-06-19T18:00:00', i3.resolved_at = '2026-06-19T20:30:00',
    i3.description = 'PaymentService cascading failure - TransactionService also down'
MERGE (pmt)-[:HAS_INCIDENT]->(i3);

MATCH (db:Service {name: 'Database'})
MERGE (i4:Incident {id: 'INC-004'}) SET i4.type = 'latency', i4.severity = 'warning', i4.status = 'resolved',
    i4.started_at = '2026-06-26T19:10:00', i4.resolved_at = '2026-06-26T19:45:00',
    i4.description = 'Database slow queries affecting PaymentService'
MERGE (db)-[:HAS_INCIDENT]->(i4);

MATCH (auth:Service {name: 'AuthService'})
MERGE (i5:Incident {id: 'INC-005'}) SET i5.type = 'timeout', i5.severity = 'minor', i5.status = 'resolved',
    i5.started_at = '2026-07-03T14:30:00', i5.resolved_at = '2026-07-03T14:45:00',
    i5.description = 'AuthService intermittent timeout'
MERGE (auth)-[:HAS_INCIDENT]->(i5);

// === 6. Propagation ===
MATCH (i3:Incident {id: 'INC-003'}), (i4:Incident {id: 'INC-004'})
MERGE (i3)-[:PROPAGATES_TO]->(i4);

// === 7. Hypotheses ===
MERGE (h1:Hypothesis {id: 'HYP-001'})
SET h1.text = 'PaymentService падает по вечерам пятницы из-за перегрузки connection pool в Database',
    h1.confidence = 0.65, h1.status = 'active', h1.created_by = 'ouroboros',
    h1.created_at = datetime(), h1.last_checked_at = datetime(),
    h1.evidence_count = 1, h1.tags = [];

MERGE (e1:Evidence {id: 'HYP-001-ev-1'})
SET e1.text = '3 из 4 последних пятниц (INC-001, INC-002, INC-003) — latency spike в PaymentService перед падением',
    e1.weight = 0.7, e1.source_type = 'pattern', e1.supports_hypothesis = true,
    e1.created_at = datetime();
MATCH (h1:Hypothesis {id: 'HYP-001'}), (e1:Evidence {id: 'HYP-001-ev-1'}) MERGE (h1)-[:HAS_EVIDENCE]->(e1);
MATCH (h1:Hypothesis {id: 'HYP-001'}), (i1:Incident {id: 'INC-001'}) MERGE (h1)-[:RELATES_TO]->(i1);
MATCH (h1:Hypothesis {id: 'HYP-001'}), (i2:Incident {id: 'INC-002'}) MERGE (h1)-[:RELATES_TO]->(i2);
MATCH (h1:Hypothesis {id: 'HYP-001'}), (i3:Incident {id: 'INC-003'}) MERGE (h1)-[:RELATES_TO]->(i3);

MERGE (h2:Hypothesis {id: 'HYP-002'})
SET h2.text = 'AuthService timeout связан с повышенной нагрузкой на APIGateway в часы пик',
    h2.confidence = 0.35, h2.status = 'active', h2.created_by = 'ouroboros',
    h2.created_at = datetime(), h2.last_checked_at = datetime(),
    h2.evidence_count = 1, h2.tags = [];

MERGE (e2:Evidence {id: 'HYP-002-ev-1'})
SET e2.text = 'INC-005 — единичный случай, данных недостаточно',
    e2.weight = 0.3, e2.source_type = 'incident', e2.supports_hypothesis = true,
    e2.created_at = datetime();
MATCH (h2:Hypothesis {id: 'HYP-002'}), (e2:Evidence {id: 'HYP-002-ev-1'}) MERGE (h2)-[:HAS_EVIDENCE]->(e2);
MATCH (h2:Hypothesis {id: 'HYP-002'}), (i5:Incident {id: 'INC-005'}) MERGE (h2)-[:RELATES_TO]->(i5);

MERGE (h3:Hypothesis {id: 'HYP-003'})
SET h3.text = 'Database slow queries — причина каскадных отказов PaymentService → TransactionService',
    h3.confidence = 0.50, h3.status = 'active', h3.created_by = 'human',
    h3.created_at = datetime(), h3.last_checked_at = datetime(),
    h3.evidence_count = 1, h3.tags = [];

MERGE (e3:Evidence {id: 'HYP-003-ev-1'})
SET e3.text = 'INC-004 показывает прямую связь Database latency → PaymentService timeout',
    e3.weight = 0.6, e3.source_type = 'incident', e3.supports_hypothesis = true,
    e3.created_at = datetime();
MATCH (h3:Hypothesis {id: 'HYP-003'}), (e3:Evidence {id: 'HYP-003-ev-1'}) MERGE (h3)-[:HAS_EVIDENCE]->(e3);
MATCH (h3:Hypothesis {id: 'HYP-003'}), (i4:Incident {id: 'INC-004'}) MERGE (h3)-[:RELATES_TO]->(i4);

// === 8. Seed completion marker ===
CREATE (:Meta {key: 'schema_version', value: '1.0', seeded_at: datetime()});
