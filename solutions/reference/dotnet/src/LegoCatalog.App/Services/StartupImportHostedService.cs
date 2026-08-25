using LegoCatalog.App.Configuration;
using LegoCatalog.App.Data;
using Microsoft.EntityFrameworkCore;

namespace LegoCatalog.App.Services;

/// <summary>
/// Applies the contract migration and completes optional idempotent startup import.
/// </summary>
public sealed class StartupImportHostedService : BackgroundService
{
    private readonly IServiceProvider _services;
    private readonly CatalogRuntimeOptions _options;
    private readonly StartupState _state;
    private readonly ILogger<StartupImportHostedService> _logger;

    public StartupImportHostedService(
        IServiceProvider services,
        CatalogRuntimeOptions options,
        StartupState state,
        ILogger<StartupImportHostedService> logger)
    {
        _services = services;
        _options = options;
        _state = state;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            await using var scope = _services.CreateAsyncScope();
            var database = scope.ServiceProvider.GetRequiredService<CatalogDbContext>();
            await database.Database.MigrateAsync(stoppingToken);
            await PreserveContractMigrationHistoryAsync(database, stoppingToken);

            if (_options.StartupImportEnabled)
            {
                if (!File.Exists(_options.SeedPath))
                {
                    throw new FileNotFoundException(
                        "Configured catalog seed file was not found.",
                        _options.SeedPath);
                }

                await using var stream = File.OpenRead(_options.SeedPath);
                var importer = scope.ServiceProvider.GetRequiredService<ImportService>();
                var result = await importer.ImportAsync(stream, stoppingToken);
                _logger.LogInformation(
                    "Startup import completed: inserted={Inserted} skipped={Skipped}",
                    result.Inserted,
                    result.Skipped);
            }

            _state.MarkReady();
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _state.MarkFailed();
            _logger.LogCritical(
                exception,
                "Startup migration or import failed; readiness remains unavailable.");
        }
    }

    /// <summary>
    /// Preserves the frozen source-era migration identity after a newer EF runtime applies it.
    /// </summary>
    private static Task<int> PreserveContractMigrationHistoryAsync(
        CatalogDbContext database,
        CancellationToken cancellationToken)
    {
        return database.Database.ExecuteSqlRawAsync(
            """
            UPDATE [__EFMigrationsHistory]
            SET [ProductVersion] = N'8.0.22'
            WHERE [MigrationId] = N'202608180001_ContractBaseline'
              AND [ProductVersion] <> N'8.0.22';
            """,
            cancellationToken);
    }
}
