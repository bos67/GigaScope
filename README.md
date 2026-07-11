# GigaScope

Мониторинг и анализ инцидентов банковской инфраструктуры.

## Структура проекта

```
gigascope/
├── backend/
│   ├── api/              — GigaScope API (порт 8099, модуль Ouroboros Gateway)
│   ├── engine/           — Analysis Engine (traversal, hypothesis, confidence)
│   ├── event_producer/   — симулятор событий для демо
│   └── scripts/          — deploy/setup скрипты
├── frontend/
│   ├── gigascope-spa/    — Three.js SPA (3D-граф зависимостей)
│   └── assets/           — иконки, стили
├── db/
│   └── cypher/           — Cypher-скрипты для Neo4j
├── docs/
│   ├── architecture.md
│   └── demo-scenario.md
└── infra/
    └── deploy.sh
```

## Архитектура

См. `docs/architecture.md`
