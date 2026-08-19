package com.microsoft.microhack.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.microsoft.microhack.catalog.config.CatalogRuntimeOptions;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

/** Verifies managed database and Blob configuration boundaries. */
class AzureConfigurationTest {

    @Test
    void managedIdentityAndBlobRequireTheWorkloadClientId() {
        Map<String, Object> values = defaults();
        values.put("CATALOG_DATABASE_AUTHENTICATION", "managed-identity");
        values.remove("CATALOG_DATABASE_PASSWORD");
        values.put("CATALOG_IMAGE_PROVIDER", "azure-blob");
        values.put("CATALOG_BLOB_SERVICE_ENDPOINT", "https://catalog.blob.core.windows.net");
        values.put("CATALOG_BLOB_CONTAINER", "catalog-images");
        values.put("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000001");

        CatalogRuntimeOptions options = CatalogRuntimeOptions.from(environment(values), "test");

        assertThat(options.databaseAuthentication())
                .isEqualTo(CatalogRuntimeOptions.DatabaseAuthentication.MANAGED_IDENTITY);
        assertThat(options.imageProvider())
                .isEqualTo(CatalogRuntimeOptions.ImageProvider.AZURE_BLOB);
        assertThat(options.blobContainerName()).isEqualTo("catalog-images");
    }

    @Test
    void managedIdentityRejectsDatabasePassword() {
        Map<String, Object> values = defaults();
        values.put("CATALOG_DATABASE_AUTHENTICATION", "managed-identity");
        values.put("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000001");

        assertThatThrownBy(() -> CatalogRuntimeOptions.from(environment(values), "test"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("forbids CATALOG_DATABASE_PASSWORD");
    }

    @Test
    void blobProviderRejectsAnInsecureEndpoint() {
        Map<String, Object> values = defaults();
        values.put("CATALOG_IMAGE_PROVIDER", "azure-blob");
        values.put("CATALOG_BLOB_SERVICE_ENDPOINT", "http://catalog.blob.core.windows.net");
        values.put("CATALOG_BLOB_CONTAINER", "catalog-images");
        values.put("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000001");

        assertThatThrownBy(() -> CatalogRuntimeOptions.from(environment(values), "test"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("must use HTTPS");
    }

    private static StandardEnvironment environment(Map<String, Object> values) {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(new MapPropertySource("test", values));
        return environment;
    }

    private static Map<String, Object> defaults() {
        Map<String, Object> values = new HashMap<>();
        values.put("CATALOG_DATABASE_HOST", "localhost");
        values.put("CATALOG_DATABASE_PORT", "5432");
        values.put("CATALOG_DATABASE_NAME", "catalog");
        values.put("CATALOG_DATABASE_USERNAME", "catalog");
        values.put("CATALOG_DATABASE_PASSWORD", "local-password");
        values.put("CATALOG_IMAGES_PATH", ".");
        values.put("CATALOG_SEED_PATH", "catalog.json");
        values.put("CATALOG_STARTUP_IMPORT_ENABLED", "false");
        values.put("PERFTEST_API_KEY", "test-api-key");
        values.put("OTEL_SERVICE_VERSION", "test");
        values.put("DEPLOYMENT_ENVIRONMENT", "lab");
        values.put("CONTAINER_APP_REVISION", "test");
        values.put("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317");
        return values;
    }
}
