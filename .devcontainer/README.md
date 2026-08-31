# Development container

This is the environment the workshop assumes. It gives you **both stacks**, a Docker
daemon, and the Azure tooling — so you never have to install .NET, Java, Maven or the Azure
CLI on your own machine.

Open it in **GitHub Codespaces** (green *Code* button → *Codespaces* → *Create codespace*),
or locally in VS Code with *Dev Containers: Reopen in Container*.

## What is inside

| | |
| --- | --- |
| .NET SDK | 8.0.424 (the version the app uses today) **and** 10.0.400 (the upgrade target) |
| Java | Microsoft Build of OpenJDK **21** by default, with **17** also installed |
| Maven | 3.9.x |
| Docker | docker-in-docker, so `docker build`, `docker run` and Testcontainers all work |
| Azure | Azure CLI with Bicep, Azure Developer CLI (`azd`), GitHub CLI |
| VS Code | C#, Java pack, Bicep, Docker, Container Apps, GitHub Copilot and Copilot Chat |

The Java tests use **Testcontainers**, which needs a working Docker daemon — that is why
docker-in-docker is enabled rather than a mounted host socket.

## Databases for local work

No database runs by default, so the container stays small and starts quickly. Start the one
your stack needs when you want to run the application locally.

**SQL Server** (for the `dotnet-sqlserver` stack):

```bash
docker run -d --name catalog-sql -p 1433:1433 \
  -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='<choose-a-strong-password>' \
  mcr.microsoft.com/mssql/server:2022-latest
```

**PostgreSQL** (for the `java-postgresql` stack):

```bash
docker run -d --name catalog-pg -p 5432:5432 \
  -e POSTGRES_PASSWORD='<choose-a-strong-password>' \
  postgres:18
```

Then set the `CATALOG_DATABASE_*` environment variables described in
[`dotnet/README.md`](../dotnet/README.md) or [`java/README.md`](../java/README.md) and start
the application. Never commit the password.

## Switching Java versions

Java 21 is the default. The application currently targets 17, and builds fine on 21. If you
need 17 explicitly:

```bash
sdk use java 17.0.20+1-ms   # `sdk list java` shows what is installed
```

## Machine size

`hostRequirements` asks for 4 cores and 8 GB. A 2-core codespace works for editing, but
building both stacks while a database container runs is uncomfortable on it.

> The image is built for **linux/amd64**, which is what Codespaces runs. That also matters
> for the databases above: the SQL Server 2022 image has no arm64 build, so on an Apple
> Silicon Mac it only runs under emulation.
