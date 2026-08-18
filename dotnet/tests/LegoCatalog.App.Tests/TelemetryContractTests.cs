using System.Diagnostics;
using System.Diagnostics.Metrics;
using LegoCatalog.App.Data;
using LegoCatalog.App.Middleware;
using LegoCatalog.App.Models;
using LegoCatalog.App.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Routing.Patterns;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace LegoCatalog.App.Tests;

public sealed class TelemetryContractTests
{
    [Fact]
    public async Task QueryTraceMetricAndFailureLogUseFrozenNames()
    {
        var activities = new List<Activity>();
        using var activityListener = new ActivityListener
        {
            ShouldListenTo = source =>
                source.Name == CatalogTelemetry.InstrumentationName,
            Sample = static (ref ActivityCreationOptions<ActivityContext> _) =>
                ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activities.Add,
        };
        ActivitySource.AddActivityListener(activityListener);

        var measurements = new List<Measurement>();
        using var meterListener = new MeterListener();
        meterListener.InstrumentPublished = (instrument, listener) =>
        {
            if (instrument.Meter.Name == CatalogTelemetry.InstrumentationName)
            {
                listener.EnableMeasurementEvents(instrument);
            }
        };
        meterListener.SetMeasurementEventCallback<double>(
            (instrument, value, tags, _) =>
                measurements.Add(
                    new Measurement(
                        instrument.Name,
                        instrument.Unit,
                        value,
                        tags.ToArray())));
        meterListener.SetMeasurementEventCallback<long>(
            (instrument, value, tags, _) =>
                measurements.Add(
                    new Measurement(
                        instrument.Name,
                        instrument.Unit,
                        value,
                        tags.ToArray())));
        meterListener.Start();

        using var telemetry = new CatalogTelemetry();
        var logger = new CapturingLogger<FigureCatalogService>();
        var service = new FigureCatalogService(
            new EmptyFigureRepository(),
            new EmptyCategoryRepository(),
            telemetry,
            logger);

        Assert.Empty(
            await service.ListAsync(
                category: "space-explorers",
                search: null,
                CancellationToken.None));
        telemetry.RecordImport(inserted: 1, skipped: 2);
        telemetry.RecordRejectedImport();
        telemetry.RecordPerformance(elapsedSeconds: 0.005, workFactor: 10);

        var queryActivity = Assert.Single(
            activities,
            activity => activity.OperationName == "catalog.query");
        Assert.Equal(
            "category",
            queryActivity.GetTagItem("catalog.query.filter"));
        Assert.Equal(0, queryActivity.GetTagItem("catalog.query.result_count"));
        Assert.Contains(
            measurements,
            measurement =>
                measurement.Name == "catalog.query.duration"
                && measurement.Unit == "s"
                && measurement.HasTag("catalog.query.filter", "category"));
        Assert.Contains(
            measurements,
            measurement =>
                measurement.Name == "db.client.operation.duration"
                && measurement.Unit == "s"
                && measurement.HasTag("db.operation.name", "select"));
        Assert.Contains(
            measurements,
            measurement =>
                measurement.Name == "catalog.import.records"
                && measurement.Unit == "{record}"
                && measurement.HasTag("catalog.import.outcome", "inserted"));
        Assert.Contains(
            measurements,
            measurement =>
                measurement.Name == "catalog.import.records"
                && measurement.Value == 1
                && measurement.HasTag("catalog.import.outcome", "rejected"));
        Assert.Contains(
            measurements,
            measurement =>
                measurement.Name == "catalog.performance.duration"
                && measurement.Unit == "s"
                && measurement.Value == 0.005
                && measurement.HasTag("catalog.performance.work_factor", 10));

        var failingLogger = new CapturingLogger<FigureCatalogService>();
        var failingService = new FigureCatalogService(
            new FailingFigureRepository(),
            new EmptyCategoryRepository(),
            telemetry,
            failingLogger);
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => failingService.ListAsync(
                null,
                null,
                CancellationToken.None));

        Assert.Contains("catalog.query.failed", failingLogger.Message);
        Assert.Equal("all", failingLogger.Scope["catalog.query.filter"]);
        Assert.Equal(
            typeof(InvalidOperationException).FullName,
            failingLogger.Scope["exception.type"]);
    }

    [Fact]
    public async Task RejectedDocumentRecordsExactlyOneRejectedUnit()
    {
        var measurements = new List<Measurement>();
        using var meterListener = new MeterListener();
        meterListener.InstrumentPublished = (instrument, listener) =>
        {
            if (instrument.Meter.Name == CatalogTelemetry.InstrumentationName)
            {
                listener.EnableMeasurementEvents(instrument);
            }
        };
        meterListener.SetMeasurementEventCallback<long>(
            (instrument, value, tags, _) =>
                measurements.Add(
                    new Measurement(
                        instrument.Name,
                        instrument.Unit,
                        value,
                        tags.ToArray())));
        meterListener.Start();

        using var telemetry = new CatalogTelemetry();
        await using var database = new CatalogDbContext(
            new DbContextOptionsBuilder<CatalogDbContext>().Options);
        var importer = new ImportService(
            database,
            new CatalogDocumentParser(),
            telemetry,
            new CapturingLogger<ImportService>());
        await using var invalidDocument = new MemoryStream("{}"u8.ToArray());

        await Assert.ThrowsAsync<CatalogImportValidationException>(
            () => importer.ImportAsync(invalidDocument, CancellationToken.None));

        var rejected = Assert.Single(
            measurements,
            measurement =>
                measurement.Name == "catalog.import.records"
                && measurement.HasTag("catalog.import.outcome", "rejected"));
        Assert.Equal(1, rejected.Value);
    }

    [Fact]
    public async Task RequestLogUsesMatchedRouteAndFinalStatus()
    {
        var logger = new CapturingLogger<RequestTelemetryMiddleware>();
        var endpoint = new RouteEndpoint(
            _ => Task.CompletedTask,
            RoutePatternFactory.Parse("/figure/{id}"),
            order: 0,
            new EndpointMetadataCollection(),
            displayName: "figure");
        var middleware = new RequestTelemetryMiddleware(
            context =>
            {
                context.SetEndpoint(endpoint);
                context.Response.StatusCode = StatusCodes.Status200OK;
                return Task.CompletedTask;
            },
            logger);
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;

        await middleware.InvokeAsync(context);

        Assert.Equal("http.server.request", logger.Message);
        Assert.Equal("GET", logger.Scope["http.request.method"]);
        Assert.Equal("/figure/{id}", logger.Scope["http.route"]);
        Assert.Equal(200, logger.Scope["http.response.status_code"]);
    }

    [Fact]
    public void ResourceIdentityUsesFrozenValues()
    {
        Assert.Equal("mh-catalog-dotnet", CatalogTelemetry.ServiceName);
        Assert.Equal("app-innovation", CatalogTelemetry.ServiceNamespace);
        Assert.Equal(
            "deployment.environment",
            CatalogTelemetry.DeploymentEnvironmentAttribute);
        Assert.Equal(
            "azure.containerapps.revision.name",
            CatalogTelemetry.RevisionAttribute);
    }

    private sealed record Measurement(
        string Name,
        string? Unit,
        double Value,
        KeyValuePair<string, object?>[] Tags)
    {
        public bool HasTag(string name, object value) =>
            Tags.Any(
                tag => tag.Key == name
                    && Equals(tag.Value, value));
    }

    private sealed class EmptyFigureRepository : IFigureRepository
    {
        public Task<IReadOnlyList<LegoFigure>> ListAsync(
            string? category,
            string? search,
            CancellationToken cancellationToken) =>
            Task.FromResult<IReadOnlyList<LegoFigure>>(
                Array.Empty<LegoFigure>());

        public Task<LegoFigure?> GetAsync(
            Guid id,
            CancellationToken cancellationToken) =>
            Task.FromResult<LegoFigure?>(null);
    }

    private sealed class FailingFigureRepository : IFigureRepository
    {
        public Task<IReadOnlyList<LegoFigure>> ListAsync(
            string? category,
            string? search,
            CancellationToken cancellationToken) =>
            throw new InvalidOperationException("expected test failure");

        public Task<LegoFigure?> GetAsync(
            Guid id,
            CancellationToken cancellationToken) =>
            Task.FromResult<LegoFigure?>(null);
    }

    private sealed class EmptyCategoryRepository : ICategoryRepository
    {
        public Task<IReadOnlyList<Category>> ListAsync(
            CancellationToken cancellationToken) =>
            Task.FromResult<IReadOnlyList<Category>>(Array.Empty<Category>());
    }

    private sealed class CapturingLogger<T> : ILogger<T>
    {
        public Dictionary<string, object> Scope { get; } = new();

        public string Message { get; private set; } = string.Empty;

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull
        {
            if (state is IEnumerable<KeyValuePair<string, object>> values)
            {
                foreach (var value in values)
                {
                    Scope[value.Key] = value.Value;
                }
            }

            return NullScope.Instance;
        }

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter) =>
            Message = formatter(state, exception);

        private sealed class NullScope : IDisposable
        {
            public static NullScope Instance { get; } = new();

            public void Dispose()
            {
            }
        }
    }
}
