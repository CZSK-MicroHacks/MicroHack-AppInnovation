using LegoCatalog.App.Services;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;

namespace LegoCatalog.App.Tests;

internal sealed class ContractWebApplicationFactory
    : WebApplicationFactory<Program>
{
    private readonly bool _databaseReady;
    private readonly StartupStatus _startupStatus;
    private readonly PerformanceBehavior _performanceBehavior;

    public ContractWebApplicationFactory(
        bool databaseReady = true,
        StartupStatus startupStatus = StartupStatus.Ready,
        PerformanceBehavior performanceBehavior = PerformanceBehavior.Success)
    {
        Environment.SetEnvironmentVariable("PERFTEST_API_KEY", "test-api-key");
        _databaseReady = databaseReady;
        _startupStatus = startupStatus;
        _performanceBehavior = performanceBehavior;
    }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.ConfigureAppConfiguration(
            configuration => configuration.AddInMemoryCollection(
                new Dictionary<string, string?>
                {
                    ["PERFTEST_API_KEY"] = "test-api-key",
                    ["CATALOG_STARTUP_IMPORT_ENABLED"] = "false",
                }));
        builder.ConfigureServices(
            services =>
            {
                services.RemoveAll<IHostedService>();
                services.RemoveAll<ICatalogDatabaseHealth>();
                services.AddScoped<ICatalogDatabaseHealth>(
                    _ => new FakeDatabaseHealth(_databaseReady));
                services.RemoveAll<IPerformanceCatalogService>();
                services.AddScoped<IPerformanceCatalogService>(
                    _ => new FakePerformanceService(_performanceBehavior));
                services.RemoveAll<StartupState>();
                var startup = new StartupState();
                if (_startupStatus == StartupStatus.Ready)
                {
                    startup.MarkReady();
                }
                else if (_startupStatus == StartupStatus.Failed)
                {
                    startup.MarkFailed();
                }

                services.AddSingleton(startup);
            });
    }

    private sealed class FakeDatabaseHealth : ICatalogDatabaseHealth
    {
        private readonly bool _ready;

        public FakeDatabaseHealth(bool ready) => _ready = ready;

        public Task<bool> CanConnectAsync(CancellationToken cancellationToken) =>
            Task.FromResult(_ready);
    }

    private sealed class FakePerformanceService : IPerformanceCatalogService
    {
        private readonly PerformanceBehavior _behavior;

        public FakePerformanceService(PerformanceBehavior behavior) =>
            _behavior = behavior;

        public Task<PerformanceResult> ExecuteAsync(
            CancellationToken cancellationToken) =>
            _behavior switch
            {
                PerformanceBehavior.DependencyUnavailable =>
                    throw new CatalogDependencyUnavailableException(),
                PerformanceBehavior.Timeout =>
                    throw new CatalogQueryTimeoutException(),
                _ => Task.FromResult(
                    new PerformanceResult(
                        10,
                        0,
                        1,
                        Array.Empty<CatalogFigureDto>())),
            };
    }
}

internal enum PerformanceBehavior
{
    Success,
    DependencyUnavailable,
    Timeout,
}
