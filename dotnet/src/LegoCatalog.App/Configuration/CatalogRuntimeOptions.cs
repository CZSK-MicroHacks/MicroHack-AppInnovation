using Microsoft.Data.SqlClient;

namespace LegoCatalog.App.Configuration;

/// <summary>
/// Holds validated process configuration shared by catalog services.
/// </summary>
public sealed record CatalogRuntimeOptions(
    string SqlConnectionString,
    string ImagesPath,
    CatalogImageProvider ImageProvider,
    Uri? BlobServiceEndpoint,
    string? BlobContainerName,
    string? WorkloadIdentityClientId,
    string SeedPath,
    bool StartupImportEnabled,
    string PerformanceApiKey,
    int PerformanceWorkFactor,
    string ServiceVersion,
    string DeploymentEnvironment,
    string RevisionName)
{
    public const int DefaultWorkFactor = 10;
    public const int MaximumWorkFactor = 25;

    /// <summary>
    /// Reads and validates the frozen environment/configuration contract.
    /// </summary>
    public static CatalogRuntimeOptions Load(
        IConfiguration configuration,
        string contentRootPath)
    {
        var host = Required(
            configuration,
            "CATALOG_DATABASE_HOST",
            "Catalog:Database:Host");
        var database = Required(
            configuration,
            "CATALOG_DATABASE_NAME",
            "Catalog:Database:Name");
        var authentication = ParseDatabaseAuthentication(
            configuration["CATALOG_DATABASE_AUTHENTICATION"]);
        var username = Optional(
            configuration,
            "CATALOG_DATABASE_USERNAME",
            "Catalog:Database:Username");
        var password = Optional(
            configuration,
            "CATALOG_DATABASE_PASSWORD",
            "Catalog:Database:Password");
        if (authentication == CatalogDatabaseAuthentication.ManagedIdentity
            && (username is not null || password is not null))
        {
            throw new InvalidOperationException(
                "Managed identity database authentication forbids username and password configuration.");
        }

        if (authentication == CatalogDatabaseAuthentication.Local
            && string.IsNullOrWhiteSpace(username) != string.IsNullOrWhiteSpace(password))
        {
            throw new InvalidOperationException(
                "CATALOG_DATABASE_USERNAME and CATALOG_DATABASE_PASSWORD must be configured together.");
        }

        var port = ParseOptionalPort(configuration["CATALOG_DATABASE_PORT"]);
        var isManagedHost = host.EndsWith(
            ".database.windows.net",
            StringComparison.OrdinalIgnoreCase);
        var connection = new SqlConnectionStringBuilder
        {
            DataSource = port is null ? host : $"{host},{port}",
            InitialCatalog = database,
            Encrypt = isManagedHost,
            TrustServerCertificate = !isManagedHost,
            ConnectTimeout = 5,
            ApplicationName = "mh-catalog-dotnet",
            MultipleActiveResultSets = false,
            PersistSecurityInfo = false,
        };
        var workloadIdentityClientId = Optional(configuration, "AZURE_CLIENT_ID");
        if (authentication == CatalogDatabaseAuthentication.ManagedIdentity)
        {
            if (!isManagedHost)
            {
                throw new InvalidOperationException(
                    "Managed identity database authentication requires an Azure SQL host.");
            }

            connection.Authentication = SqlAuthenticationMethod.ActiveDirectoryManagedIdentity;
            connection.UserID = workloadIdentityClientId
                ?? throw new InvalidOperationException(
                    "AZURE_CLIENT_ID is required for managed identity database authentication.");
        }
        else if (username is null)
        {
            connection.IntegratedSecurity = true;
        }
        else
        {
            connection.UserID = username;
            connection.Password = password;
        }

        var imagesPath = ResolvePath(
            Required(configuration, "CATALOG_IMAGES_PATH", "Catalog:ImagesPath"),
            contentRootPath);
        var imageProvider = ParseImageProvider(
            configuration["CATALOG_IMAGE_PROVIDER"]);
        Uri? blobServiceEndpoint = null;
        string? blobContainerName = null;
        if (imageProvider == CatalogImageProvider.AzureBlob)
        {
            var endpoint = Required(configuration, "CATALOG_BLOB_SERVICE_ENDPOINT");
            if (!Uri.TryCreate(endpoint, UriKind.Absolute, out blobServiceEndpoint)
                || blobServiceEndpoint.Scheme != Uri.UriSchemeHttps)
            {
                throw new InvalidOperationException(
                    "CATALOG_BLOB_SERVICE_ENDPOINT must be an absolute HTTPS URI.");
            }

            blobContainerName = Required(configuration, "CATALOG_BLOB_CONTAINER");
            workloadIdentityClientId ??= Required(configuration, "AZURE_CLIENT_ID");
        }
        var seedPath = ResolvePath(
            Required(configuration, "CATALOG_SEED_PATH", "Catalog:SeedPath"),
            contentRootPath);
        var startupImportEnabled = ParseBoolean(
            configuration["CATALOG_STARTUP_IMPORT_ENABLED"]
                ?? configuration["Catalog:StartupImportEnabled"],
            defaultValue: true,
            "CATALOG_STARTUP_IMPORT_ENABLED");
        var apiKey = Required(configuration, "PERFTEST_API_KEY");
        var workFactor = ParseWorkFactor(configuration["PERFTEST_WORK_FACTOR"]);
        var deploymentEnvironment =
            configuration["DEPLOYMENT_ENVIRONMENT"]?.Trim() ?? "lab";
        if (!string.Equals(deploymentEnvironment, "lab", StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "DEPLOYMENT_ENVIRONMENT must be 'lab' for the workshop contract.");
        }

        return new CatalogRuntimeOptions(
            connection.ConnectionString,
            imagesPath,
            imageProvider,
            blobServiceEndpoint,
            blobContainerName,
            workloadIdentityClientId,
            seedPath,
            startupImportEnabled,
            apiKey,
            workFactor,
            configuration["OTEL_SERVICE_VERSION"]?.Trim() ?? "1.0.0",
            deploymentEnvironment,
            configuration["CONTAINER_APP_REVISION"]?.Trim() ?? "local");
    }

    /// <summary>
    /// Parses the bounded performance work factor.
    /// </summary>
    public static int ParseWorkFactor(string? rawValue)
    {
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return DefaultWorkFactor;
        }

        if (!int.TryParse(rawValue, out var parsed)
            || parsed < 1
            || parsed > MaximumWorkFactor)
        {
            throw new InvalidOperationException(
                $"PERFTEST_WORK_FACTOR must be an integer from 1 through {MaximumWorkFactor}.");
        }

        return parsed;
    }

    private static CatalogDatabaseAuthentication ParseDatabaseAuthentication(
        string? rawValue)
    {
        return rawValue?.Trim() switch
        {
            null or "" or "local" => CatalogDatabaseAuthentication.Local,
            "managed-identity" => CatalogDatabaseAuthentication.ManagedIdentity,
            _ => throw new InvalidOperationException(
                "CATALOG_DATABASE_AUTHENTICATION must be 'local' or 'managed-identity'."),
        };
    }

    private static CatalogImageProvider ParseImageProvider(string? rawValue)
    {
        return rawValue?.Trim() switch
        {
            null or "" or "local" => CatalogImageProvider.Local,
            "azure-blob" => CatalogImageProvider.AzureBlob,
            _ => throw new InvalidOperationException(
                "CATALOG_IMAGE_PROVIDER must be 'local' or 'azure-blob'."),
        };
    }

    private static int? ParseOptionalPort(string? rawValue)
    {
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return null;
        }

        if (!int.TryParse(rawValue, out var port) || port is < 1 or > 65535)
        {
            throw new InvalidOperationException(
                "CATALOG_DATABASE_PORT must be an integer from 1 through 65535.");
        }

        return port;
    }

    private static bool ParseBoolean(
        string? rawValue,
        bool defaultValue,
        string name)
    {
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return defaultValue;
        }

        if (!bool.TryParse(rawValue, out var parsed))
        {
            throw new InvalidOperationException($"{name} must be true or false.");
        }

        return parsed;
    }

    private static string ResolvePath(string path, string contentRootPath)
    {
        return Path.GetFullPath(
            Path.IsPathRooted(path) ? path : Path.Combine(contentRootPath, path));
    }

    private static string Required(
        IConfiguration configuration,
        string key,
        string? fallbackKey = null)
    {
        return Optional(configuration, key, fallbackKey)
            ?? throw new InvalidOperationException($"{key} is required.");
    }

    private static string? Optional(
        IConfiguration configuration,
        string key,
        string? fallbackKey = null)
    {
        var value = configuration[key]
            ?? (fallbackKey is null ? null : configuration[fallbackKey]);
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }
}

public enum CatalogDatabaseAuthentication
{
    Local,
    ManagedIdentity,
}

public enum CatalogImageProvider
{
    Local,
    AzureBlob,
}
