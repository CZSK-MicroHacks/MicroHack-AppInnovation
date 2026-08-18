using System.Text;
using System.Text.Json;
using LegoCatalog.App.Services;

namespace LegoCatalog.App.Tests;

public sealed class ConformanceVectorTests
{
    [Fact]
    public void CategorySlugMatchesSharedVectors()
    {
        using var document = JsonDocument.Parse(
            File.ReadAllText(ContractPath("normalization-vectors.json")));
        foreach (var vector in document.RootElement.GetProperty("vectors").EnumerateArray())
        {
            Assert.Equal(
                vector.GetProperty("expected").GetString(),
                CategorySlug.Normalize(vector.GetProperty("input").GetString()!));
        }

        foreach (var vector in document.RootElement
            .GetProperty("invalidVectors")
            .EnumerateArray())
        {
            Assert.Empty(
                CategorySlug.Normalize(vector.GetProperty("input").GetString()!));
        }
    }

    [Fact]
    public async Task IdentityMatchesSharedVectors()
    {
        var parser = new CatalogDocumentParser();
        using var document = JsonDocument.Parse(
            File.ReadAllText(ContractPath("identity-vectors.json")));
        foreach (var vector in document.RootElement.GetProperty("vectors").EnumerateArray())
        {
            var payload = JsonSerializer.Serialize(
                new[]
                {
                    new
                    {
                        productId = vector.GetProperty("productId").GetString(),
                        name = "Contract Figure",
                        description =
                            "A representative figure used to validate shared identity behavior.",
                        category = "Contract Figures",
                        filename = vector.GetProperty("filename").GetString(),
                        imagePrompt =
                            "Photorealistic construction-toy figure on a clean studio background.",
                    },
                });
            await using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
            if (vector.GetProperty("valid").GetBoolean())
            {
                Assert.Single(await parser.ParseAsync(stream, CancellationToken.None));
            }
            else
            {
                await Assert.ThrowsAsync<CatalogImportValidationException>(
                    () => parser.ParseAsync(stream, CancellationToken.None));
            }
        }
    }

    [Fact]
    public async Task UnicodeCategoryAndWholeDocumentValidationAreStable()
    {
        var parser = new CatalogDocumentParser();
        await using var valid = File.OpenRead(
            Path.Combine(
                RepositoryRoot(),
                "tests",
                "acceptance",
                "fixtures",
                "catalog.valid.json"));

        var items = await parser.ParseAsync(valid, CancellationToken.None);

        Assert.Equal("lete-artists", items[0].CategorySlug);

        await using var invalid = File.OpenRead(
            Path.Combine(
                RepositoryRoot(),
                "tests",
                "acceptance",
                "fixtures",
                "catalog.invalid.json"));
        await Assert.ThrowsAsync<CatalogImportValidationException>(
            () => parser.ParseAsync(invalid, CancellationToken.None));
    }

    private static string ContractPath(string fileName) =>
        Path.Combine(RepositoryRoot(), "workshop", "contracts", fileName);

    private static string RepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, "workshop", "contracts")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Repository root was not found.");
    }
}
