# Java/PostgreSQL catalog baseline

This directory contains one intentionally monolithic Spring Boot 3.5.16 application for
Microsoft OpenJDK 17.0.20+8 and PostgreSQL 18.6. It uses Spring MVC, Thymeleaf, JPA schema
validation, and the Flyway-owned `V1__contract_baseline.sql` migration. It contains no
student-facing container image or Azure infrastructure.

## Prerequisites

- Microsoft OpenJDK 17.0.20+8
- Docker 27.4 or a PostgreSQL 18.6 service
- `psql` 18.6 for full database acceptance
- `uv` 0.8.22 and Python 3.12 for the shared acceptance harness

The Maven Wrapper is version 3.3.4 and downloads checksum-pinned Maven 3.9.16.

## Configuration

Supply every secret outside source control:

| Variable | Requirement |
| --- | --- |
| `CATALOG_DATABASE_HOST` | PostgreSQL host |
| `CATALOG_DATABASE_PORT` | Optional port, default `5432`, range 1-65535 |
| `CATALOG_DATABASE_NAME` | Database name |
| `CATALOG_DATABASE_USERNAME` | Database application identity |
| `CATALOG_DATABASE_PASSWORD` | Database password |
| `CATALOG_DATABASE_SSL_MODE` | PostgreSQL JDBC SSL mode; use `disable` only locally |
| `CATALOG_IMAGES_PATH` | Absolute or working-directory-relative canonical image directory |
| `CATALOG_SEED_PATH` | Absolute or working-directory-relative `catalog.json` |
| `CATALOG_STARTUP_IMPORT_ENABLED` | `true` or `false`; default `true` |
| `PERFTEST_API_KEY` | Required non-default API key |
| `PERFTEST_WORK_FACTOR` | Optional integer 1-25; default `10` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Absolute HTTP(S) OTLP endpoint |
| `OTEL_SERVICE_VERSION` | Deployed source/version identity |
| `DEPLOYMENT_ENVIRONMENT` | Required value `lab` |
| `CONTAINER_APP_REVISION` | Revision identity; use a local label during development |

Standard `OTEL_*` exporter variables configure protocol, headers, TLS, sampling, and
timeouts. Set `OTEL_SDK_DISABLED=true` only when intentionally running without a collector.

Catalog imports validate and write through a proxied transaction worker. The surrounding
telemetry boundary reports completion only after commit and records one rejected document when
parsing, validation, persistence, or transaction commit fails.

## Local PostgreSQL and run

The disposable database below uses the frozen multi-platform PostgreSQL image digest:

```bash
docker run -d --name mh-java-postgres \
  -e POSTGRES_DB=catalog \
  -e POSTGRES_USER=catalog \
  -e POSTGRES_PASSWORD="<local-password>" \
  -p 5432:5432 \
  "postgres:18.6-bookworm@sha256:7d2695c3aa88e792e8b3b233e7e4adb296a20412c6c0ca361e3edaaacfada108"

export CATALOG_DATABASE_HOST=localhost
export CATALOG_DATABASE_PORT=5432
export CATALOG_DATABASE_NAME=catalog
export CATALOG_DATABASE_USERNAME=catalog
export CATALOG_DATABASE_PASSWORD="<local-password>"
export CATALOG_DATABASE_SSL_MODE=disable
export CATALOG_IMAGES_PATH="../data/images"
export CATALOG_SEED_PATH="../data/catalog.json"
export CATALOG_STARTUP_IMPORT_ENABLED=true
export PERFTEST_API_KEY="<local-api-key>"
export PERFTEST_WORK_FACTOR=10
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export OTEL_SERVICE_VERSION="local"
export DEPLOYMENT_ENVIRONMENT=lab
export CONTAINER_APP_REVISION=local
export OTEL_SDK_DISABLED=true

./mvnw spring-boot:run
```

Open `http://localhost:8080/`. Liveness is `/healthz`; readiness is `/readyz`.

## Test and package

```bash
./mvnw test
./mvnw package
java -jar target/catalog-java-1.0.0.jar
```

Surefire writes native JUnit XML to `target/surefire-reports/`, including all fourteen
frozen runtime display names and their package-qualified test classes. The conformance
suite reads both shared normalization and text-validation vector files directly from
`workshop/contracts`.

## Full shared acceptance

Run from `tests/acceptance` while the JAR and database are running:

```bash
export CATALOG_BASE_URL="http://localhost:8080"
export CATALOG_DATABASE_KIND=postgresql
export CATALOG_DATABASE_TARGET=local
uv run pytest -q
uv lock --check --offline
uv run python -m catalog_acceptance \
  --profile full \
  --base-url "$CATALOG_BASE_URL" \
  --performance-api-key "$PERFTEST_API_KEY" \
  --database-kind postgresql \
  --database-host "$CATALOG_DATABASE_HOST" \
  --database-port "$CATALOG_DATABASE_PORT" \
  --database-name "$CATALOG_DATABASE_NAME" \
  --database-username "$CATALOG_DATABASE_USERNAME" \
  --database-password "$CATALOG_DATABASE_PASSWORD" \
  --database-ssl-mode disable \
  --database-target local \
  --output /tmp/java-acceptance-report.json
```

## Outage, recovery, and clean database

Stop PostgreSQL and verify `/healthz` remains exactly healthy while `/readyz` and the
authorized performance endpoint report their frozen dependency failures:

```bash
docker stop mh-java-postgres
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/readyz
curl -i -H "x-api-key: $PERFTEST_API_KEY" http://localhost:8080/perftest/catalog
docker start mh-java-postgres
curl -i http://localhost:8080/readyz
```

To prove a clean database, remove and recreate only the disposable container. Flyway
recreates the exact schema and startup import restores 198 figures and 20 categories:

```bash
docker rm -f mh-java-postgres
# Repeat the docker run command above, then restart the JAR.
```
