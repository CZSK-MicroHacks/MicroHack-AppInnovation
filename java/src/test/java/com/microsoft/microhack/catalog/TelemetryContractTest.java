package com.microsoft.microhack.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.microsoft.microhack.catalog.config.CatalogResourceIdentity;
import com.microsoft.microhack.catalog.config.CatalogRuntimeOptions;
import com.microsoft.microhack.catalog.repository.CategoryRepository;
import com.microsoft.microhack.catalog.repository.FigureRepository;
import com.microsoft.microhack.catalog.service.CatalogDocumentParser;
import com.microsoft.microhack.catalog.service.CatalogImportService;
import com.microsoft.microhack.catalog.service.CatalogImportValidationException;
import com.microsoft.microhack.catalog.service.CatalogService;
import com.microsoft.microhack.catalog.service.CatalogTelemetry;
import com.microsoft.microhack.catalog.service.CatalogQueryTimeoutException;
import com.microsoft.microhack.catalog.service.PerformanceCatalogService;
import com.microsoft.microhack.catalog.web.RequestTelemetryFilter;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import jakarta.validation.Validation;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

/** Proves frozen telemetry with real SDK exporters and structured log events. */
class TelemetryContractTest {

    private InMemorySpanExporter spans;
    private InMemoryMetricReader metrics;
    private SdkTracerProvider tracerProvider;
    private SdkMeterProvider meterProvider;
    private CatalogTelemetry telemetry;
    private CatalogRuntimeOptions options;

    @BeforeEach
    void configureSdk() {
        options = new CatalogRuntimeOptions(
                "database.internal",
                "catalog",
                Path.of("images"),
                Path.of("catalog.json"),
                true,
                "test-key",
                3,
                "1.0-test",
                "lab",
                "revision-test",
                "instance-test",
                "http://localhost:4317");
        AttributesBuilder attributes = Attributes.builder();
        CatalogResourceIdentity.attributes(options).forEach(attributes::put);
        Resource resource = Resource.create(attributes.build());

        spans = InMemorySpanExporter.create();
        metrics = InMemoryMetricReader.create();
        tracerProvider = SdkTracerProvider.builder()
                .setResource(resource)
                .addSpanProcessor(SimpleSpanProcessor.create(spans))
                .build();
        meterProvider = SdkMeterProvider.builder()
                .setResource(resource)
                .registerMetricReader(metrics)
                .build();
        OpenTelemetrySdk sdk = OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setMeterProvider(meterProvider)
                .build();
        telemetry = new CatalogTelemetry(sdk, options);
    }

    @AfterEach
    void closeSdk() {
        meterProvider.close();
        tracerProvider.close();
        spans.close();
    }

    @Test
    void httpServerSpanMetricAndResourceIdentityAreExported() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/healthz");
        request.setServerName("catalog.test");
        MockHttpServletResponse response = new MockHttpServletResponse();
        new RequestTelemetryFilter(telemetry).doFilter(
                request,
                response,
                (ignoredRequest, ignoredResponse) -> response.setStatus(204));

        var span = spans.getFinishedSpanItems().get(0);
        assertThat(span.getKind()).isEqualTo(SpanKind.SERVER);
        assertThat(span.getAttributes().get(
                io.opentelemetry.api.common.AttributeKey.stringKey("http.route")))
                .isEqualTo("/healthz");
        CatalogResourceIdentity.attributes(options).forEach((name, value) ->
                assertThat(span.getResource().getAttribute(
                        io.opentelemetry.api.common.AttributeKey.stringKey(name)))
                        .isEqualTo(value));
        assertThat(metricNames()).contains(CatalogTelemetry.HTTP_DURATION_METRIC);
    }

    @Test
    void rejectedImportExportsFailureSpanMetricAndStructuredLog() {
        FigureRepository figures = mock(FigureRepository.class);
        CategoryRepository categories = mock(CategoryRepository.class);
        CatalogDocumentParser parser = new CatalogDocumentParser(
                new ObjectMapper(),
                Validation.buildDefaultValidatorFactory().getValidator());
        CatalogImportService service =
                new CatalogImportService(parser, figures, categories, telemetry);
        ListAppender<ILoggingEvent> logs = capture(CatalogImportService.class);

        assertThatThrownBy(() -> service.importDocument(new ByteArrayInputStream(
                        "null".getBytes(StandardCharsets.UTF_8))))
                .isInstanceOf(CatalogImportValidationException.class);

        var span = spans.getFinishedSpanItems().stream()
                .filter(item -> item.getName().equals("catalog.import"))
                .findFirst()
                .orElseThrow();
        assertThat(span.getAttributes().get(
                io.opentelemetry.api.common.AttributeKey.longKey("catalog.import.rejected")))
                .isEqualTo(1L);
        assertThat(span.getEvents()).anyMatch(event -> event.getName().equals("exception"));
        assertThat(metricNames()).contains("catalog.import.records");
        assertThat(logs.list).anySatisfy(event -> {
            assertThat(event.getFormattedMessage()).isEqualTo("catalog.import.failed");
            assertThat(event.getMDCPropertyMap())
                    .containsEntry("catalog.import.rejected", "1")
                    .containsKey("exception.type");
        });
        verifyNoInteractions(figures, categories);
    }

    @Test
    void queryFailureExportsDatabaseAndFilterEvidence() {
        FigureRepository figures = mock(FigureRepository.class);
        CategoryRepository categories = mock(CategoryRepository.class);
        when(figures.findAllByOrderByIdAsc())
                .thenThrow(new DataAccessResourceFailureException("database unavailable"));
        ListAppender<ILoggingEvent> logs = capture(CatalogService.class);

        assertThatThrownBy(() -> new CatalogService(figures, categories, telemetry)
                        .list(null, null))
                .isInstanceOf(DataAccessResourceFailureException.class);

        Map<String, io.opentelemetry.sdk.trace.data.SpanData> exported =
                spans.getFinishedSpanItems().stream().collect(java.util.stream.Collectors.toMap(
                        item -> item.getName(), item -> item));
        assertThat(exported.get("db.client").getKind()).isEqualTo(SpanKind.CLIENT);
        assertThat(exported.get("catalog.query").getAttributes().get(
                io.opentelemetry.api.common.AttributeKey.stringKey("catalog.query.filter")))
                .isEqualTo("all");
        assertThat(logs.list).extracting(ILoggingEvent::getFormattedMessage)
                .contains("catalog.database.failed", "catalog.query.failed");
        assertThat(logs.list.stream()
                        .filter(event -> event.getFormattedMessage().equals("catalog.query.failed"))
                        .findFirst()
                        .orElseThrow()
                        .getMDCPropertyMap())
                .containsEntry("catalog.query.filter", "all")
                .containsKey("exception.type");
        assertThat(metricNames())
                .contains(CatalogTelemetry.DATABASE_DURATION_METRIC,
                        CatalogTelemetry.QUERY_DURATION_METRIC);
    }

    @Test
    void performanceFailureExportsWorkFactorAndDatabaseEvidence() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        CatalogService catalog = mock(CatalogService.class);
        when(jdbc.queryForObject(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.eq(Long.class)))
                .thenThrow(new QueryTimeoutException("bounded work timed out"));
        ListAppender<ILoggingEvent> logs = capture(PerformanceCatalogService.class);

        assertThatThrownBy(() ->
                        new PerformanceCatalogService(jdbc, catalog, options, telemetry).execute())
                .isInstanceOf(CatalogQueryTimeoutException.class);

        var span = spans.getFinishedSpanItems().stream()
                .filter(item -> item.getName().equals("catalog.performance"))
                .findFirst()
                .orElseThrow();
        assertThat(span.getAttributes().get(
                io.opentelemetry.api.common.AttributeKey.longKey(
                        "catalog.performance.work_factor")))
                .isEqualTo(3L);
        assertThat(logs.list).extracting(ILoggingEvent::getFormattedMessage)
                .contains("catalog.database.failed", "catalog.performance.failed");
        assertThat(logs.list.stream()
                        .filter(event ->
                                event.getFormattedMessage().equals("catalog.performance.failed"))
                        .findFirst()
                        .orElseThrow()
                        .getMDCPropertyMap())
                .containsEntry("catalog.performance.work_factor", "3")
                .containsKey("exception.type");
        assertThat(metricNames()).contains(CatalogTelemetry.DATABASE_DURATION_METRIC);
    }

    private ListAppender<ILoggingEvent> capture(Class<?> type) {
        Logger logger = (Logger) LoggerFactory.getLogger(type);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        return appender;
    }

    private List<String> metricNames() {
        return metrics.collectAllMetrics().stream().map(MetricData::getName).toList();
    }
}
