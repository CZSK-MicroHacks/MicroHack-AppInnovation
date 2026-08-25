using Azure;
using Azure.Identity;
using Azure.Storage.Blobs;
using LegoCatalog.App.Configuration;

namespace LegoCatalog.App.Services;

/// <summary>
/// Reads canonical image objects from Blob Storage with the workload identity.
/// </summary>
public sealed class AzureBlobImageStore : IImageStore
{
    private readonly BlobContainerClient _container;

    public AzureBlobImageStore(CatalogRuntimeOptions options)
        : this(CreateContainerClient(options))
    {
    }

    public AzureBlobImageStore(BlobContainerClient container)
    {
        _container = container;
    }

    public string GetImageUrl(string fileName) => $"/images/{fileName}";

    public async Task<ReadOnlyMemory<byte>?> ReadAsync(
        string fileName,
        CancellationToken cancellationToken)
    {
        if (!LocalImageStore.IsCanonicalImageKey(fileName))
        {
            return null;
        }

        try
        {
            var response = await _container
                .GetBlobClient(fileName)
                .DownloadContentAsync(cancellationToken);
            return response.Value.Content.ToMemory();
        }
        catch (RequestFailedException exception) when (exception.Status == 404)
        {
            return null;
        }
    }

    private static BlobContainerClient CreateContainerClient(
        CatalogRuntimeOptions options)
    {
        if (options.BlobServiceEndpoint is null
            || options.BlobContainerName is null
            || options.WorkloadIdentityClientId is null)
        {
            throw new InvalidOperationException(
                "Azure Blob image configuration is incomplete.");
        }

        var credential = new ManagedIdentityCredential(
            ManagedIdentityId.FromUserAssignedClientId(
                options.WorkloadIdentityClientId));
        return new BlobServiceClient(options.BlobServiceEndpoint, credential)
            .GetBlobContainerClient(options.BlobContainerName);
    }
}
