# Домашка 1 — приложение в контейнере + мониторинг + CI/CD

## Что это

Учебное веб-приложение «Заметки» (Flask + SQLite): можно добавлять,
редактировать и удалять заметки прямо в браузере — то есть интерфейс не
просто открывается, а даёт что-то реально потыкать и отредактировать.
Само содержимое неважно, важен пайплайн вокруг него.

Эндпоинты:
- `/` — веб-интерфейс
- `/health` — health check (используется Docker HEALTHCHECK, compose и CI)
- `/metrics` — метрики в формате Prometheus: потребляемая/доступная память,
  число ядер CPU, load average, место на диске, число посещений всего и
  за последний час

## Структура репозитория

```
app/                      исходный код приложения
Dockerfile                описание образа
docker-compose.yml        приложение + весь стек мониторинга
monitoring/prometheus.yml конфиг Prometheus (что скрейпить)
scripts/build.sh          сборка образа + сохранение артефакта (.tar)
scripts/deploy.sh         разворачивание артефакта на сервере
scripts/run_local.sh      запуск всего одной командой для проверки
.github/workflows/ci-cd.yml   CI/CD пайплайн (build → artifact → registry → deploy)
```

## Как проверить локально (для преподавателя)

Нужен только Docker + Docker Compose:

```bash
git clone <ссылка на репозиторий>
cd homework1
./scripts/run_local.sh
```

Скрипт соберёт образ, поднимет приложение и весь стек мониторинга и
проверит `/health`. После этого открыть:

- приложение: http://localhost:8000
- метрики приложения: http://localhost:8000/metrics
- Prometheus (сырые метрики/графики): http://localhost:9090
- Grafana (дашборды): http://localhost:3000 (admin/admin)

Остановить: `docker compose down`

## CI/CD процесс (`.github/workflows/ci-cd.yml`)

При пуше в `main` пайплайн выполняет три шага:

1. **build** — собирает Docker-образ из исходников, поднимает его и
   проверяет `/health` (smoke test), затем сохраняет образ как файл
   (`docker save`) и загружает его как **артефакт сборки** в GitHub Actions
   (доступен на вкладке Actions → конкретный run → Artifacts).
2. **push** — публикует тот же образ в container registry (GHCR),
   помеченный хешем коммита и `latest`.
3. **deploy** — по SSH подключается к серверу, скачивает свежий образ
   (`docker pull`) и пересоздаёт контейнер приложения через
   `docker compose up -d --force-recreate`, не трогая volume с данными
   (заметки сохраняются между деплоями).

Ручной путь (без GitHub Actions), эквивалентный этому пайплайну:

```bash
# на машине разработчика / в CI
./scripts/build.sh                       # сборка + сохранение .tar артефакта

# перенос артефакта на сервер, например:
scp artifacts/homework1-app-*.tar user@server:/opt/homework1/artifacts/
scp docker-compose.yml monitoring/prometheus.yml user@server:/opt/homework1/

# на сервере
cd /opt/homework1
./scripts/deploy.sh artifacts/homework1-app-<tag>.tar
```

## Мониторинг

- **node-exporter** — метрики ресурсов всей машины (сколько CPU/памяти
  всего доступно и сколько занято на хосте).
- **cAdvisor** — метрики ресурсов именно контейнера приложения (сколько
  CPU/памяти реально потребляет `hw1-app`).
- **приложение само** отдаёт на `/metrics`: uptime, RSS процесса,
  `app_visits_total` и `app_visits_last_hour` — метрика использования
  приложения, которую требовалось добавить отдельно.
- **Prometheus** скрейпит все три источника (`monitoring/prometheus.yml`).
- **Grafana** — для визуализации (данные можно смотреть и напрямую в
  Prometheus по адресу `:9090`, если не настраивать отдельный дашборд).
- **health check** — встроен в `Dockerfile` (`HEALTHCHECK`), в
  `docker-compose` через него же, и отдельно проверяется в CI и в
  `deploy.sh`/`run_local.sh`.

## Данные (редактируемость приложения)

Заметки хранятся в SQLite-файле на Docker volume `app-data`, который
не пересоздаётся при `--force-recreate` контейнера — то есть можно
редактировать данные через интерфейс, передеплоить новую версию образа,
и данные останутся на месте.
