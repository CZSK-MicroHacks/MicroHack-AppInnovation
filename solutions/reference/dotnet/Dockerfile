# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/dotnet/sdk:10.0.400-azurelinux3.0-amd64@sha256:679e7b7e9d0315ad34438bee49b4fb0658c4c42a3aa08ae8557d1bd03f49c28b AS build
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

FROM mcr.microsoft.com/dotnet/aspnet:10.0.11-azurelinux3.0-amd64@sha256:d21a49ce9556f5e50afc5a33cc45ec7a40b5739f10397368810193666e559a79
WORKDIR /app
RUN mkdir -p /app/data /app/images && chown -R 1654:1654 /app
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
