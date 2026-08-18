package com.microsoft.microhack.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.microsoft.microhack.catalog.config.CatalogRuntimeOptions;
import com.microsoft.microhack.catalog.service.CatalogTelemetry;
import org.junit.jupiter.api.Test;

/** Pins custom telemetry and resource attribute names to the shared contract. */
class TelemetryContractTest {

    @Test
    void resourceIdentityAndInstrumentationNamesAreFrozen() {
        assertThat(CatalogTelemetry.SERVICE_NAME).isEqualTo("mh-catalog-java");
        assertThat(CatalogTelemetry.SERVICE_NAMESPACE).isEqualTo("app-innovation");
        assertThat(CatalogTelemetry.DEPLOYMENT_ENVIRONMENT_ATTRIBUTE)
                .isEqualTo("deployment.environment");
        assertThat(CatalogTelemetry.REVISION_ATTRIBUTE)
                .isEqualTo("azure.containerapps.revision.name");
        assertThat(CatalogRuntimeOptions.SERVICE_NAME).isEqualTo(CatalogTelemetry.SERVICE_NAME);
        assertThat(CatalogTelemetry.DATABASE_DURATION_METRIC)
                .isEqualTo("db.client.operation.duration");
        assertThat(CatalogTelemetry.DATABASE_DURATION_UNIT).isEqualTo("s");
        assertThat(CatalogTelemetry.QUERY_DURATION_METRIC).isEqualTo("catalog.query.duration");
        assertThat(CatalogTelemetry.PERFORMANCE_DURATION_METRIC)
                .isEqualTo("catalog.performance.duration");
    }
}
