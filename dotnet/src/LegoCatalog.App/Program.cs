using Azure.Monitor.OpenTelemetry.Exporter;
using LegoCatalog.App.Configuration;
using LegoCatalog.App.Data;
using LegoCatalog.App.Endpoints;
using LegoCatalog.App.Middleware;
using LegoCatalog.App.Services;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);
var runtime = CatalogRuntimeOptions.Load(
    builder.Configuration,
    builder.Environment.ContentRootPath);
builder.Services.AddSingleton(runtime);

builder.Services.AddDbContext<CatalogDbContext>(
    options => options.UseSqlServer(
        runtime.SqlConnectionString,
        sqlServer => sqlServer
            .CommandTimeout(15)
            .EnableRetryOnFailure()));
builder.Services.AddRazorPages();
builder.Services.AddServerSideBlazor();
builder.Services.Configure<FormOptions>(
    options => options.MultipartBodyLengthLimit = 4 * 1024 * 1024);

builder.Services.AddSingleton<CatalogTelemetry>();
builder.Services.AddSingleton<StartupState>();
builder.Services.AddSingleton<CatalogDocumentParser>();
builder.Services.AddScoped<IFigureRepository, FigureRepository>();
builder.Services.AddScoped<ICategoryRepository, CategoryRepository>();
builder.Services.AddScoped<IImageStore>(
    provider => runtime.ImageProvider == CatalogImageProvider.AzureBlob
        ? new AzureBlobImageStore(runtime)
        : new LocalImageStore(runtime));
builder.Services.AddScoped<ICatalogDatabaseHealth, CatalogDatabaseHealth>();
builder.Services.AddScoped<FigureCatalogService>();
builder.Services.AddScoped<ImportService>();
builder.Services.AddScoped<IPerformanceCatalogService, PerformanceCatalogService>();
builder.Services.AddHostedService<StartupImportHostedService>();

var hasOtlpExporter = new[]
{
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
}.Any(key => !string.IsNullOrWhiteSpace(builder.Configuration[key]));

// Kept independent of hasOtlpExporter on purpose. The deployment sets
// APPLICATIONINSIGHTS_CONNECTION_STRING and no OTLP endpoint, so folding the
// two together would leave Azure Monitor silently unconfigured while the app
// still started and reported healthy.
var applicationInsightsConnectionString =
    builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"];
var hasAzureMonitorExporter =
    !string.IsNullOrWhiteSpace(applicationInsightsConnectionString);

builder.Services
    .AddOpenTelemetry()
    .ConfigureResource(
        resource => resource
            .AddService(
                serviceName: CatalogTelemetry.ServiceName,
                serviceNamespace: CatalogTelemetry.ServiceNamespace,
                serviceVersion: runtime.ServiceVersion,
                serviceInstanceId: Environment.MachineName)
            .AddAttributes(
                new Dictionary<string, object>
                {
                    [CatalogTelemetry.DeploymentEnvironmentAttribute] =
                        runtime.DeploymentEnvironment,
                    [CatalogTelemetry.RevisionAttribute] = runtime.RevisionName,
                }))
    .WithMetrics(
        metrics =>
        {
            metrics
                .AddAspNetCoreInstrumentation()
                .AddHttpClientInstrumentation()
                .AddRuntimeInstrumentation()
                .AddMeter(CatalogTelemetry.InstrumentationName);
            if (hasOtlpExporter)
            {
                metrics.AddOtlpExporter();
            }

            if (hasAzureMonitorExporter)
            {
                metrics.AddAzureMonitorMetricExporter(
                    options => options.ConnectionString =
                        applicationInsightsConnectionString);
            }
        })
    .WithTracing(
        tracing =>
        {
            tracing
                .AddAspNetCoreInstrumentation(
                    options => options.RecordException = true)
                .AddHttpClientInstrumentation()
                .AddSqlClientInstrumentation()
                .AddSource(CatalogTelemetry.InstrumentationName);
            if (hasOtlpExporter)
            {
                tracing.AddOtlpExporter();
            }

            if (hasAzureMonitorExporter)
            {
                tracing.AddAzureMonitorTraceExporter(
                    options => options.ConnectionString =
                        applicationInsightsConnectionString);
            }
        });

builder.Logging.AddOpenTelemetry(
    logging =>
    {
        logging.IncludeFormattedMessage = true;
        logging.IncludeScopes = true;
        if (hasOtlpExporter)
        {
            logging.AddOtlpExporter();
        }

        if (hasAzureMonitorExporter)
        {
            logging.AddAzureMonitorLogExporter(
                options => options.ConnectionString =
                    applicationInsightsConnectionString);
        }
    });

var app = builder.Build();
app.UseMiddleware<OriginalRequestTargetMiddleware>();
app.UseStaticFiles();
app.UseRouting();
app.UseMiddleware<RequestTelemetryMiddleware>();
app.UseExceptionHandler("/Error");
app.MapCatalogEndpoints();
app.MapRazorPages();
app.MapBlazorHub();
app.MapFallbackToPage("/import", "/_Host");
app.Run();

public partial class Program;
