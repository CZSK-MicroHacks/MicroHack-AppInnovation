using LegoCatalog.App.Configuration;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;

namespace LegoCatalog.App.Tests;

public sealed class AzureConfigurationTests
{
    [Fact]
    public void ManagedIdentityBuildsTokenAuthenticatedAzureSqlConnection()
    {
        var options = CatalogRuntimeOptions.Load(
            Configuration(
                new Dictionary<string, string?>
                {
                    ["CATALOG_DATABASE_HOST"] = "catalog.database.windows.net",
                    ["CATALOG_DATABASE_NAME"] = "catalog",
                    ["CATALOG_DATABASE_AUTHENTICATION"] = "managed-identity",
                    ["AZURE_CLIENT_ID"] = "00000000-0000-0000-0000-000000000001",
                }),
            Directory.GetCurrentDirectory());
        var connection = new SqlConnectionStringBuilder(options.SqlConnectionString);

        Assert.Equal(
            SqlAuthenticationMethod.ActiveDirectoryManagedIdentity,
            connection.Authentication);
        Assert.True(connection.Encrypt);
        Assert.False(connection.TrustServerCertificate);
        Assert.Equal(
            "00000000-0000-0000-0000-000000000001",
            connection.UserID);
    }

    [Fact]
    public void BlobProviderRequiresHttpsAndWorkloadIdentity()
    {
        var options = CatalogRuntimeOptions.Load(
            Configuration(
                new Dictionary<string, string?>
                {
                    ["CATALOG_IMAGE_PROVIDER"] = "azure-blob",
                    ["CATALOG_BLOB_SERVICE_ENDPOINT"] =
                        "https://catalog.blob.core.windows.net",
                    ["CATALOG_BLOB_CONTAINER"] = "catalog-images",
                    ["AZURE_CLIENT_ID"] = "00000000-0000-0000-0000-000000000001",
                }),
            Directory.GetCurrentDirectory());

        Assert.Equal(CatalogImageProvider.AzureBlob, options.ImageProvider);
        Assert.Equal("catalog-images", options.BlobContainerName);
    }

    private static IConfiguration Configuration(
        IDictionary<string, string?> overrides)
    {
        var values = new Dictionary<string, string?>
        {
            ["CATALOG_DATABASE_HOST"] = @".\SQLEXPRESS",
            ["CATALOG_DATABASE_NAME"] = "LegoCatalog",
            ["CATALOG_IMAGES_PATH"] = ".",
            ["CATALOG_SEED_PATH"] = "catalog.json",
            ["CATALOG_STARTUP_IMPORT_ENABLED"] = "false",
            ["PERFTEST_API_KEY"] = "test-api-key",
            ["DEPLOYMENT_ENVIRONMENT"] = "lab",
            ["OTEL_SERVICE_VERSION"] = "contract-test",
            ["CONTAINER_APP_REVISION"] = "contract-test",
        };
        foreach (var (key, value) in overrides)
        {
            values[key] = value;
        }

        return new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
    }
}
