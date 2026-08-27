# syntax=docker/dockerfile:1.7
FROM --platform=linux/amd64 mcr.microsoft.com/dotnet/sdk:8.0.424-bookworm-slim-amd64@sha256:237133a0ea20cffcfaa92588e1c8a56d58fe99f44da72dcff35aeb017119abcf AS build
WORKDIR /src
COPY dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj dotnet/src/LegoCatalog.App/
RUN dotnet restore dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj \
    --runtime linux-x64 \
    --source https://www.nuget.org/api/v2/
COPY dotnet/src/LegoCatalog.App/ dotnet/src/LegoCatalog.App/
RUN dotnet publish dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj \
    --configuration Release \
    --runtime linux-x64 \
    --no-restore \
    --self-contained false \
    --output /out

FROM --platform=linux/amd64 mcr.microsoft.com/dotnet/aspnet:8.0.22-bookworm-slim-amd64@sha256:405899493453fb0a64b1ac5a1d869f928817a9b47bdc2ea22407ab6c2bfbdf63
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data /app/images \
    && chown -R 1654:1654 /app
COPY --from=build --chown=1654:1654 /out/ /app/
COPY --chown=0:0 data/catalog.json /app/data/catalog.json
RUN chmod 0444 /app/data/catalog.json
USER 1654
ENV ASPNETCORE_URLS=http://0.0.0.0:8080 \
    CATALOG_SEED_PATH=/app/data/catalog.json \
    CATALOG_IMAGES_PATH=/app/images
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8080/healthz"]
ENTRYPOINT ["dotnet", "LegoCatalog.App.dll"]
