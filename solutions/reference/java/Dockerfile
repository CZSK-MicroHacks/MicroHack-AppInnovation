# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/openjdk/jdk:21-azurelinux@sha256:06ec8d4b09883cb695aa37e3ae85d1188f124b6dbcfeff97eeb09a926f7c389f AS build
WORKDIR /src
RUN tdnf install -y unzip && tdnf clean all
COPY java/.mvn/ java/.mvn/
COPY java/mvnw java/pom.xml java/
RUN cd java && ./mvnw -q -DskipTests dependency:go-offline
COPY java/src/ java/src/
RUN cd java && ./mvnw -q package -DskipTests

FROM mcr.microsoft.com/openjdk/jdk:21-azurelinux@sha256:06ec8d4b09883cb695aa37e3ae85d1188f124b6dbcfeff97eeb09a926f7c389f
WORKDIR /app
RUN mkdir -p /app/data /app/images && chown -R 10001:0 /app
COPY --from=build --chown=10001:0 /src/java/target/catalog-java-1.0.0.jar /app/catalog.jar
COPY --chown=0:0 data/catalog.json /app/data/catalog.json
RUN chmod 0444 /app/data/catalog.json
USER 10001
ENV HOME=/tmp \
    SERVER_PORT=8080 \
    CATALOG_SEED_PATH=/app/data/catalog.json \
    CATALOG_IMAGES_PATH=/app/images
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8080/healthz"]
ENTRYPOINT ["java", "-jar", "/app/catalog.jar"]
