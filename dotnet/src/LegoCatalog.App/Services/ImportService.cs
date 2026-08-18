using System.Diagnostics;
using LegoCatalog.App.Data;
using LegoCatalog.App.Models;
using Microsoft.EntityFrameworkCore;

namespace LegoCatalog.App.Services;

/// <summary>
/// Publishes a validated catalog document atomically and idempotently.
/// </summary>
public sealed class ImportService
{
    private readonly CatalogDbContext _database;
    private readonly CatalogDocumentParser _parser;
    private readonly CatalogTelemetry _telemetry;
    private readonly ILogger<ImportService> _logger;

    public ImportService(
        CatalogDbContext database,
        CatalogDocumentParser parser,
        CatalogTelemetry telemetry,
        ILogger<ImportService> logger)
    {
        _database = database;
        _parser = parser;
        _telemetry = telemetry;
        _logger = logger;
    }

    /// <summary>
    /// Validates the complete stream, then commits all new categories and figures once.
    /// </summary>
    public async Task<ImportResult> ImportAsync(
        Stream jsonStream,
        CancellationToken cancellationToken)
    {
        IReadOnlyList<ValidatedCatalogItem> items;
        try
        {
            items = await _parser.ParseAsync(jsonStream, cancellationToken);
        }
        catch (CatalogImportValidationException exception)
        {
            LogFailure(exception.RejectedCount, exception);
            throw;
        }

        using var activity = _telemetry.StartActivity("catalog.import");
        try
        {
            var strategy = _database.Database.CreateExecutionStrategy();
            var result = await strategy.ExecuteAsync(async () =>
            {
                await using var transaction =
                    await _database.Database.BeginTransactionAsync(cancellationToken);
                var categories = await _database.Categories
                    .ToListAsync(cancellationToken);
                var categoriesByName = categories.ToDictionary(
                    category => category.Name,
                    StringComparer.OrdinalIgnoreCase);
                var categoriesBySlug = categories.ToDictionary(
                    category => category.Slug,
                    StringComparer.Ordinal);
                var existingIds = (
                    await _database.Figures
                        .AsNoTracking()
                        .Select(figure => figure.Id)
                        .ToListAsync(cancellationToken))
                    .ToHashSet();
                var inserted = 0;
                var now = DateTime.UtcNow;

                foreach (var item in items)
                {
                    if (existingIds.Contains(item.ProductId))
                    {
                        continue;
                    }

                    if (!categoriesByName.TryGetValue(item.Category, out var category))
                    {
                        if (categoriesBySlug.TryGetValue(
                            item.CategorySlug,
                            out var conflictingCategory))
                        {
                            throw new CatalogImportValidationException(
                                $"Category '{item.Category}' conflicts with existing category '{conflictingCategory.Name}'.",
                                items.Count);
                        }

                        category = new Category
                        {
                            Name = item.Category,
                            Slug = item.CategorySlug,
                        };
                        _database.Categories.Add(category);
                        categoriesByName.Add(category.Name, category);
                        categoriesBySlug.Add(category.Slug, category);
                    }

                    _database.Figures.Add(new LegoFigure
                    {
                        Id = item.ProductId,
                        Name = item.Name,
                        Description = item.Description,
                        ImageFile = item.Filename,
                        Category = category,
                        CreatedUtc = now,
                        LastUpdatedUtc = now,
                    });
                    existingIds.Add(item.ProductId);
                    inserted++;
                }

                if (inserted > 0)
                {
                    await _database.SaveChangesAsync(cancellationToken);
                }

                await transaction.CommitAsync(cancellationToken);
                return new ImportResult(
                    inserted,
                    items.Count - inserted,
                    items.Count);
            });

            activity?.SetTag("catalog.import.inserted", result.Inserted);
            activity?.SetTag("catalog.import.skipped", result.Skipped);
            activity?.SetTag("catalog.import.rejected", 0);
            _telemetry.RecordImport(result.Inserted, result.Skipped);
            using (_logger.BeginScope(
                new Dictionary<string, object>
                {
                    ["catalog.import.inserted"] = result.Inserted,
                    ["catalog.import.skipped"] = result.Skipped,
                }))
            {
                _logger.LogInformation(
                    "catalog.import.completed inserted={Inserted} skipped={Skipped}",
                    result.Inserted,
                    result.Skipped);
            }

            return result;
        }
        catch (Exception exception)
        {
            activity?.SetStatus(ActivityStatusCode.Error, exception.Message);
            CatalogTelemetry.RecordException(activity, exception);
            activity?.SetTag("catalog.import.rejected", items.Count);
            LogFailure(items.Count, exception);
            throw;
        }
    }

    private void LogFailure(int rejected, Exception exception)
    {
        CatalogTelemetry.LogException(_logger, exception);
        using (_logger.BeginScope(
            new Dictionary<string, object>
            {
                ["catalog.import.rejected"] = rejected,
                ["exception.type"] = exception.GetType().FullName ?? exception.GetType().Name,
            }))
        {
            _logger.LogError(
                exception,
                "catalog.import.failed rejected={Rejected}",
                rejected);
        }
    }
}

public sealed record ImportResult(int Inserted, int Skipped, int Total);
