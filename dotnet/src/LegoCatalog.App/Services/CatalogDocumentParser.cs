using System.Text.Json;
using System.Text.Json.Serialization;

namespace LegoCatalog.App.Services;

/// <summary>
/// Parses and validates a complete catalog document before publication starts.
/// </summary>
public sealed class CatalogDocumentParser
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };

    /// <summary>
    /// Returns fully validated records or rejects the entire document.
    /// </summary>
    public async Task<IReadOnlyList<ValidatedCatalogItem>> ParseAsync(
        Stream jsonStream,
        CancellationToken cancellationToken)
    {
        List<CatalogInputItem>? rawItems;
        try
        {
            rawItems = await JsonSerializer.DeserializeAsync<List<CatalogInputItem>>(
                jsonStream,
                SerializerOptions,
                cancellationToken);
        }
        catch (JsonException exception)
        {
            throw new CatalogImportValidationException(
                "The catalog document is not valid contract JSON.",
                1,
                exception);
        }

        if (rawItems is null || rawItems.Count == 0)
        {
            throw new CatalogImportValidationException(
                "The catalog document must contain at least one record.",
                1);
        }

        var validated = new List<ValidatedCatalogItem>(rawItems.Count);
        var ids = new HashSet<Guid>();
        for (var index = 0; index < rawItems.Count; index++)
        {
            try
            {
                validated.Add(Validate(rawItems[index], ids));
            }
            catch (CatalogImportValidationException exception)
            {
                throw new CatalogImportValidationException(
                    $"Record {index + 1} is invalid: {exception.Message}",
                    rawItems.Count,
                    exception);
            }
        }

        return validated;
    }

    private static ValidatedCatalogItem Validate(
        CatalogInputItem item,
        ISet<Guid> ids)
    {
        RequireLength(item.Name, 3, 80, "name");
        RequireLength(item.Description, 20, 1200, "description");
        RequireLength(item.Category, 2, 60, "category");
        RequireLength(item.ImagePrompt, 30, 260, "imagePrompt");
        if (item.ProductId is null
            || !Guid.TryParseExact(item.ProductId, "D", out var productId)
            || !string.Equals(
                productId.ToString("D"),
                item.ProductId,
                StringComparison.Ordinal))
        {
            throw new CatalogImportValidationException(
                "productId must be a canonical lowercase UUID.",
                1);
        }

        if (!ids.Add(productId))
        {
            throw new CatalogImportValidationException(
                "productId values must be unique within one document.",
                1);
        }

        var expectedFilename = $"{productId:D}.png";
        if (!string.Equals(
            item.Filename,
            expectedFilename,
            StringComparison.Ordinal))
        {
            throw new CatalogImportValidationException(
                $"filename must equal {expectedFilename}.",
                1);
        }

        var category = item.Category!;
        var categorySlug = CategorySlug.Normalize(category);
        if (categorySlug.Length == 0)
        {
            throw new CatalogImportValidationException(
                "category must normalize to a non-empty slug.",
                1);
        }

        return new ValidatedCatalogItem(
            productId,
            item.Name!,
            item.Description!,
            category,
            categorySlug,
            item.Filename!);
    }

    private static void RequireLength(
        string? value,
        int minimum,
        int maximum,
        string field)
    {
        var length = value?.EnumerateRunes().Count() ?? 0;
        if (length < minimum || length > maximum)
        {
            throw new CatalogImportValidationException(
                $"{field} must contain from {minimum} through {maximum} characters.",
                1);
        }
    }

    private sealed record CatalogInputItem(
        [property: JsonPropertyName("productId")] string? ProductId,
        [property: JsonPropertyName("name")] string? Name,
        [property: JsonPropertyName("description")] string? Description,
        [property: JsonPropertyName("category")] string? Category,
        [property: JsonPropertyName("filename")] string? Filename,
        [property: JsonPropertyName("imagePrompt")] string? ImagePrompt);
}

public sealed record ValidatedCatalogItem(
    Guid ProductId,
    string Name,
    string Description,
    string Category,
    string CategorySlug,
    string Filename);

/// <summary>
/// Signals whole-document validation failure before publication.
/// </summary>
public sealed class CatalogImportValidationException : Exception
{
    public CatalogImportValidationException(
        string message,
        int rejectedCount,
        Exception? innerException = null)
        : base(message, innerException)
    {
        RejectedCount = rejectedCount;
    }

    public int RejectedCount { get; }
}
