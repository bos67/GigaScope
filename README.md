# GigaScope

GigaScope — демонстрационный контур проактивного мониторинга банковской инфраструктуры. Он показывает цифровой граф зависимостей, инциденты, гипотезы, каскады, пользовательские сигналы и прогноз риска в интерактивной Three.js SPA.

> **Важно:** этот репозиторий содержит SPA, прокси-сервер и сценарии подготовки демо. Бизнес-логика API GigaScope является модулем совместимой установки **Ouroboros** и должна быть доступна по `/api/gigascope/*`. Этот дистрибутив пока не является автономным backend-приложением.

## Что входит в дистрибутив

```text
backend/api/gigascope_server.py      SPA-сервер и прокси к Ouroboros API
backend/event_producer/              отдельный сценарий генерации событий
frontend/gigascope-spa/index.html    интерфейс GigaScope
init_topology.py                     создание исходной топологии Neo4j
demo_seeder.py                       подготовка канонического демо-состояния
reset_demo.sh                        пересоздание Neo4j и полный seed демо
requirements.txt                     Python-зависимости
config.example.env                   безопасный шаблон конфигурации
```

Рабочие логи, локальные базы, виртуальные окружения, снапшоты диалога, сгенерированные PDF и временные файлы в публичный дистрибутив не входят.

## Архитектура запуска

```text
Браузер
  │ http://localhost:8099
  ▼
GigaScope SPA proxy
  │ /api/gigascope/*
  ▼
Ouroboros API :8765
  │
  ▼
Neo4j :7687
```

SPA-прокси не содержит бизнес-логики и не хранит данные. Он отдаёт `index.html` и перенаправляет API-запросы в Ouroboros.

## Требования

- Linux или macOS; Windows — через WSL2;
- Python 3.10 или новее;
- Docker Engine с Docker CLI;
- `curl`;
- совместимый Ouroboros с включёнными маршрутами `/api/gigascope/*`;
- свободные порты `7474`, `7687`, `8099`, `8765`.

## Быстрое развёртывание

### 1. Клонировать репозиторий

```bash
git clone https://github.com/bos67/GigaScope.git gigascope
cd gigascope
```

### 2. Создать Python-окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Настроить окружение

```bash
cp config.example.env .env
set -a
source .env
set +a
```

Измените пароль в `.env` перед первым запуском. Файл `.env` запрещено коммитить.

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `OUROBOROS_API_URL` | адрес совместимого Ouroboros API | `http://localhost:8765` |
| `GIGASCOPE_SPA_HOST` | интерфейс SPA-сервера | `127.0.0.1` |
| `GIGASCOPE_SPA_PORT` | порт SPA | `8099` |
| `NEO4J_BOLT_URL` | Bolt URL Neo4j | `bolt://localhost:7687` |
| `NEO4J_USER` | пользователь Neo4j | `neo4j` |
| `NEO4J_PASSWORD` | пароль Neo4j | задаётся владельцем |
| `NEO4J_CONTAINER` | имя Docker-контейнера | `gigascope-neo4j` |
| `NEO4J_IMAGE` | Docker image Neo4j | `neo4j:5` |
| `GIGASCOPE_NEO4J_URI` | Neo4j URI внутри процесса Ouroboros | `bolt://localhost:7687` |
| `GIGASCOPE_NEO4J_USER` | Neo4j user внутри Ouroboros | `neo4j` |
| `GIGASCOPE_NEO4J_PASS` | Neo4j password внутри Ouroboros | должен совпадать с `NEO4J_PASSWORD` |
| `OPENROUTER_API_KEY` | необязательный LLM-анализ логов | пусто: endpoint вернёт HTTP 503 |

### 4. Запустить Ouroboros

GigaScope **не является автономным backend**: маршруты `/api/gigascope/*` исполняются совместимым Ouroboros. Перед его запуском задайте `GIGASCOPE_NEO4J_URI`, `GIGASCOPE_NEO4J_USER` и `GIGASCOPE_NEO4J_PASS`; пароль должен совпадать с `NEO4J_PASSWORD`, которым создаётся контейнер. `OPENROUTER_API_KEY` нужен только для LLM-анализа логов. Для endpoint метрик VM в окружении Ouroboros должен быть установлен `psutil` (он также включён в `requirements.txt`).

Запустите совместимую установку Ouroboros отдельно и убедитесь, что GigaScope API отвечает:

```bash
curl -f "$OUROBOROS_API_URL/api/gigascope/engine/status"
```

Если запрос не возвращает HTTP 200, SPA откроется, но данные и демо работать не будут.

### 5. Подготовить Neo4j и демо-данные

Скрипт ниже **удаляет и пересоздаёт** контейнер с именем `$NEO4J_CONTAINER`. Не используйте его против базы с ценными данными.

```bash
bash reset_demo.sh
```

Скрипт проверяет Docker и Ouroboros API, пересоздаёт Neo4j, запускает `init_topology.py`, затем `demo_seeder.py`.

Ручной вариант без полного reset:

```bash
docker run -d \
  --name "$NEO4J_CONTAINER" \
  -p 7474:7474 -p 7687:7687 \
  -e "NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}" \
  "$NEO4J_IMAGE"

python init_topology.py \
  --bolt-url "$NEO4J_BOLT_URL" \
  --user "$NEO4J_USER" \
  --password "$NEO4J_PASSWORD"

python demo_seeder.py \
  --base-url "$OUROBOROS_API_URL" \
  --neo4j-url "$NEO4J_BOLT_URL" \
  --neo4j-user "$NEO4J_USER" \
  --neo4j-password "$NEO4J_PASSWORD"
```

### 6. Запустить SPA

```bash
python backend/api/gigascope_server.py \
  --host "$GIGASCOPE_SPA_HOST" \
  --port "$GIGASCOPE_SPA_PORT"
```

Откройте `http://127.0.0.1:8099/`.

Для доступа с другой машины задайте `GIGASCOPE_SPA_HOST=0.0.0.0`, но сначала ограничьте доступ firewall или reverse proxy. Встроенный сервер не добавляет TLS и аутентификацию.

## Проверка работоспособности

```bash
curl -f "http://127.0.0.1:${GIGASCOPE_SPA_PORT}/"
curl -f "http://127.0.0.1:${GIGASCOPE_SPA_PORT}/api/gigascope/graph"
curl -f "$OUROBOROS_API_URL/api/gigascope/engine/status"
```

Перед записью демо ожидается подготовленный backend:

- 9 гипотез;
- 18 инцидентов;
- 7 критических инцидентов;
- граф 16 узлов / 20 связей;
- Database `failure_probability_4h` около 35,5% (в речи округляется до 36%).

При загрузке SPA презентационный baseline показывает все узлы зелёными. Нажатие **«Демо»** раскрывает подготовленные живые данные по этапам в течение 90 секунд и не записывает новые инциденты в Neo4j.

## Запуск 90-секундного демо

1. Выполните `bash reset_demo.sh`.
2. Откройте SPA и обновите страницу.
3. Убедитесь, что до старта показано `16 / 0 / 0`.
4. Начните запись экрана.
5. Один раз нажмите **«Демо»**.
6. Не взаимодействуйте с интерфейсом 90 секунд.
7. В финале проверьте 9 гипотез, 18 инцидентов и 7 критических.

Таймкод-лист следует публиковать отдельным проверенным документом в `docs/`, а не вместе с рабочими снапшотами диалога.

## Остановка

SPA останавливается `Ctrl+C` в его терминале.

```bash
docker stop "$NEO4J_CONTAINER"
# Удаляет демонстрационный контейнер и его данные:
docker rm "$NEO4J_CONTAINER"
```

## Типовые проблемы

### SPA открывается, но API отвечает 502

```bash
curl -v "$OUROBOROS_API_URL/api/gigascope/engine/status"
```

Ouroboros не запущен или `OUROBOROS_API_URL` указан неверно.

### Нет доступа к Docker

```bash
docker ps
```

Настройте права пользователя на Docker daemon. Скрипт поддерживает `sudo -n docker`, если беспарольный sudo уже настроен владельцем системы.

### Neo4j не принимает соединение

```bash
docker logs "$NEO4J_CONTAINER"
curl -f http://localhost:7474/
```

Один и тот же `NEO4J_PASSWORD` должен использоваться при создании контейнера, инициализации и запуске Ouroboros.

### После запуска демо числа не совпадают

```bash
bash reset_demo.sh
```

Не запускайте `backend/event_producer/demo_scenario.py` перед каноническим демо: он создаёт дополнительные события и предназначен для отдельной отладки.

## Безопасность перед публичной публикацией

1. Проверить `git status` и публикуемый diff.
2. Не добавлять `.env`, ключи, токены, реальные пароли, логи и дампы БД.
3. Не публиковать `dialogue-snapshots/`, локальные PDF и записи экрана без отдельного решения автора.
4. Проверить лицензию проекта и лицензии внешних frontend-библиотек.
5. Убедиться, что в истории Git нет секретов: `.gitignore` не очищает старую историю.
6. Провести запуск с чистого clone на отдельной машине или VM.

Этот репозиторий нельзя считать production-ready: встроенный SPA-сервер не обеспечивает TLS, аутентификацию, rate limiting и изоляцию сети.

## Лицензия

Проект распространяется по лицензии **BSD 2-Clause "Simplified" License**. Полный текст находится в файле [LICENSE](LICENSE).
