package com.microsoft.microhack.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.joran.JoranConfigurator;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.microsoft.microhack.catalog.config.CatalogResourceIdentity;
import com.microsoft.microhack.catalog.config.CatalogRuntimeOptions;
import com.microsoft.microhack.catalog.repository.CategoryRepository;
import com.microsoft.microhack.catalog.repository.FigureRepository;
import com.microsoft.microhack.catalog.service.CatalogDocumentParser;
import com.microsoft.microhack.catalog.service.CatalogImportService;
import com.microsoft.microhack.catalog.service.CatalogImportValidationException;
import com.microsoft.microhack.catalog.service.CatalogQueryTimeoutException;
import com.microsoft.microhack.catalog.service.CatalogService;
import com.microsoft.microhack.catalog.service.CatalogTelemetry;
import com.microsoft.microhack.catalog.service.PerformanceCatalogService;
import com.microsoft.microhack.catalog.web.RequestTelemetryFilter;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.instrumentation.logback.appender.v1_0.OpenTelemetryAppender;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.data.LogRecordData;
import io.opentelemetry.sdk.logs.export.SimpleLogRecordProcessor;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.testing.exporter.InMemoryLogRecordExporter;
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import jakarta.validation.Validation;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
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

/** Proves frozen traces, metrics, and bridged logs with real SDK exporters. */
class TelemetryContractTest {

    private InMemorySpanExporter spans;
    private InMemoryMetricReader metrics;
    private InMemoryLogRecordExporter logs;
    private SdkTracerProvider tracerProvider;
    private SdkMeterProvider meterProvider;
    private SdkLoggerProvider loggerProvider;
    private CatalogTelemetry telemetry;
    private CatalogRuntimeOptions options;

    @BeforeEach
    void configureSdkAndProductionLogbackBridge() throws Exception {
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
        logs = InMemoryLogRecordExporter.create();
        tracerProvider = SdkTracerProvider.builder()
                .setResource(resource)
                .addSpanProcessor(SimpleSpanProcessor.create(spans))
                .build();
        meterProvider = SdkMeterProvider.builder()
                .setResource(resource)
                .registerMetricReader(metrics)
                .build();
        loggerProvider = SdkLoggerProvider.builder()
                .setResource(resource)
                .addLogRecordProcessor(SimpleLogRecordProcessor.create(logs))
                .build();
        OpenTelemetrySdk sdk = OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setMeterProvider(meterProvider)
                .setLoggerProvider(loggerProvider)
                .build();
        configureProductionLogback(sdk);
        telemetry = new CatalogTelemetry(sdk, options);
    }

    @AfterEach
    void closeSdk() {
        loggerProvider.close();
        meterProvider.close();
        tracerProvider.close();
        logs.close();
        spans.close();
    }

    @Test
    void httpSignalAndFullResourceIdentityReachLogExporter() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/healthz");
        request.setServerName("catalog.test");
        MockHttpServletResponse response = new MockHttpServletResponse();
        new RequestTelemetryFilter(telemetry).doFilter(
                request,
                response,
                (ignoredRequest, ignoredResponse) -> response.setStatus(204));

        var span = spans.getFinishedSpanItems().get(0);
        assertThat(span.getKind()).isEqualTo(SpanKind.SERVER);
        assertThat(span.getAttributes().get(AttributeKey.stringKey("http.route")))
                .isEqualTo("/healthz");
        assertThat(metricNames()).contains(CatalogTelemetry.HTTP_DURATION_METRIC);
        LogRecordData record = log("http.server.request");
        assertAttributes(record, Map.of(
                "http.request.method", "GET",
                "http.route", "/healthz",
                "http.response.status_code", "204"));
        assertFullResource(record);

        logs.reset();
        assertThatThrownBy(() -> new RequestTelemetryFilter(telemetry).doFilter(
                        request,
                        response,
                        (ignoredRequest, ignoredResponse) -> {
                            throw new jakarta.servlet.ServletException("request failed");
                        }))
                .isInstanceOf(jakarta.servlet.ServletException.class);
        assertAttributes(log("exception"), Map.of(
                "exception.type", jakarta.servlet.ServletException.class.getName(),
                "exception.message", "request failed"));
    }

    @Test
    void importCompletedFailedAndExceptionSignalsReachLogExporter() {
        FigureRepository figures = mock(FigureRepository.class);
        CategoryRepository categories = mock(CategoryRepository.class);
        CatalogImportService service = importService(figures, categories);

        assertThatThrownBy(() -> service.importDocument(stream("null")))
                .isInstanceOf(CatalogImportValidationException.class);

        var span = spans.getFinishedSpanItems().stream()
                .filter(item -> item.getName().equals("catalog.import"))
                .findFirst()
                .orElseThrow();
        assertThat(span.getAttributes().get(AttributeKey.longKey("catalog.import.rejected")))
                .isEqualTo(1L);
        assertThat(span.getEvents()).anyMatch(event -> event.getName().equals("exception"));
        assertThat(metricNames()).contains("catalog.import.records");
        assertAttributes(log("catalog.import.failed"), Map.of(
                "catalog.import.rejected", "1",
                "exception.type", CatalogImportValidationException.class.getName()));
        assertExceptionRecord(CatalogImportValidationException.class);
        verifyNoInteractions(figures, categories);

        logs.reset();
        when(figures.existsById(org.mockito.ArgumentMatchers.any())).thenReturn(true);
        service.importDocument(stream(validItem()));
        assertAttributes(log("catalog.import.completed"), Map.of(
                "catalog.import.inserted", "0",
                "catalog.import.skipped", "1"));
    }

    @Test
    void databaseAndQueryFailuresExportEveryFrozenLogAttribute() {
        FigureRepository figures = mock(FigureRepository.class);
        CategoryRepository categories = mock(CategoryRepository.class);
        when(figures.findAllByOrderByIdAsc())
                .thenThrow(new DataAccessResourceFailureException("database unavailable"));

        assertThatThrownBy(() -> new CatalogService(figures, categories, telemetry)
                        .list(null, null))
                .isInstanceOf(DataAccessResourceFailureException.class);

        Map<String, io.opentelemetry.sdk.trace.data.SpanData> exported =
                spans.getFinishedSpanItems().stream().collect(java.util.stream.Collectors.toMap(
                        item -> item.getName(), item -> item));
        assertThat(exported.get("db.client").getKind()).isEqualTo(SpanKind.CLIENT);
        assertThat(exported.get("catalog.query").getAttributes().get(
                AttributeKey.stringKey("catalog.query.filter")))
                .isEqualTo("all");
        assertAttributes(log("catalog.database.failed"), Map.of(
                "db.system.name", "postgresql",
                "db.operation.name", "select",
                "exception.type", DataAccessResourceFailureException.class.getName()));
        assertAttributes(log("catalog.query.failed"), Map.of(
                "catalog.query.filter", "all",
                "exception.type", DataAccessResourceFailureException.class.getName()));
        assertThat(logs("exception")).hasSize(2).allSatisfy(record -> {
            assertAttributes(record, Map.of(
                    "exception.type", DataAccessResourceFailureException.class.getName(),
                    "exception.message", "database unavailable"));
            assertFullResource(record);
        });
        assertThat(metricNames()).contains(
                CatalogTelemetry.DATABASE_DURATION_METRIC,
                CatalogTelemetry.QUERY_DURATION_METRIC);
    }

    @Test
    void performanceCompletedFailedAndExceptionSignalsReachLogExporter() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        CatalogService catalog = mock(CatalogService.class);
        when(jdbc.queryForObject(
                        org.mockito.ArgumentMatchers.anyString(),
                        org.mockito.ArgumentMatchers.eq(Long.class)))
                .thenReturn(1L);
        when(catalog.list(null, null)).thenReturn(List.of());

        new PerformanceCatalogService(jdbc, catalog, options, telemetry).execute();
        assertAttributes(log("catalog.performance.completed"), Map.of(
                "catalog.performance.work_factor", "3",
                "catalog.performance.item_count", "0"));

        logs.reset();
        when(jdbc.queryForObject(
                        org.mockito.ArgumentMatchers.anyString(),
                        org.mockito.ArgumentMatchers.eq(Long.class)))
                .thenThrow(new QueryTimeoutException("bounded work timed out"));
        assertThatThrownBy(() ->
                        new PerformanceCatalogService(jdbc, catalog, options, telemetry).execute())
                .isInstanceOf(CatalogQueryTimeoutException.class);

        assertAttributes(log("catalog.database.failed"), Map.of(
                "db.system.name", "postgresql",
                "db.operation.name", "execute",
                "exception.type", QueryTimeoutException.class.getName()));
        assertAttributes(log("catalog.performance.failed"), Map.of(
                "catalog.performance.work_factor", "3",
                "exception.type", QueryTimeoutException.class.getName()));
        assertThat(logs("exception")).hasSize(2).allSatisfy(record -> {
            assertAttributes(record, Map.of(
                    "exception.type", QueryTimeoutException.class.getName(),
                    "exception.message", "bounded work timed out"));
            assertFullResource(record);
        });
        assertThat(metricNames()).contains(CatalogTelemetry.DATABASE_DURATION_METRIC);
    }

    private void configureProductionLogback(OpenTelemetrySdk sdk) throws Exception {
        LoggerContext context = (LoggerContext) LoggerFactory.getILoggerFactory();
        context.reset();
        JoranConfigurator configurator = new JoranConfigurator();
        configurator.setContext(context);
        try (InputStream configuration = getClass().getClassLoader()
                .getResourceAsStream("logback-spring.xml")) {
            assertThat(configuration).isNotNull();
            configurator.doConfigure(configuration);
        }
        Logger root = context.getLogger(Logger.ROOT_LOGGER_NAME);
        assertThat(root.getAppender("OPENTELEMETRY"))
                .isInstanceOf(OpenTelemetryAppender.class);
        OpenTelemetryAppender.install(sdk);
    }

    private CatalogImportService importService(
            FigureRepository figures,
            CategoryRepository categories) {
        return new CatalogImportService(
                new CatalogDocumentParser(
                        new ObjectMapper(),
                        Validation.buildDefaultValidatorFactory().getValidator()),
                figures,
                categories,
                telemetry);
    }

    private LogRecordData log(String event) {
        return logs(event).stream().findFirst().orElseThrow();
    }

    private List<LogRecordData> logs(String event) {
        return logs.getFinishedLogRecordItems().stream()
                .filter(record -> event.equals(record.getBodyValue().asString()))
                .toList();
    }

    private void assertExceptionRecord(Class<? extends Exception> type) {
        assertAttributes(log("exception"), Map.of(
                "exception.type", type.getName(),
                "exception.message", "catalog document root must be one JSON array"));
    }

    private void assertAttributes(LogRecordData record, Map<String, String> expected) {
        expected.forEach((name, value) ->
                assertThat(record.getAttributes().get(AttributeKey.stringKey(name)))
                        .as(name)
                        .isEqualTo(value));
        assertFullResource(record);
    }

    private void assertFullResource(LogRecordData record) {
        CatalogResourceIdentity.attributes(options).forEach((name, value) ->
                assertThat(record.getResource().getAttribute(AttributeKey.stringKey(name)))
                        .as(name)
                        .isEqualTo(value));
    }

    private List<String> metricNames() {
        return metrics.collectAllMetrics().stream().map(MetricData::getName).toList();
    }

    private static ByteArrayInputStream stream(String document) {
        return new ByteArrayInputStream(document.getBytes(StandardCharsets.UTF_8));
    }

    private static String validItem() {
        return """
                [{
                  "productId":"44444444-4444-4444-8444-444444444444",
                  "name":"Telemetry Figure",
                  "description":"A complete figure used to validate telemetry completion logs.",
                  "category":"Telemetry Figures",
                  "filename":"44444444-4444-4444-8444-444444444444.png",
                  "imagePrompt":"Photorealistic construction-toy figure on a clean studio background."
                }]
                """;
    }
}
