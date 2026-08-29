using Azure;
using Azure.Identity;
using Azure.Storage.Blobs;
using LegoCatalog.App.Configuration;

namespace LegoCatalog.App.Services;

/// <summary>
/// Reads catalog images from Azure Blob Storage using the workload identity.
/// </summary>
public sealed class AzureBlobImageStore : IImageStore
{
    private readonly BlobContainerClient _container;

    public AzureBlobImageStore(CatalogRuntimeOptions options)
    {
        if (options.BlobServiceEndpoint is null || options.BlobContainerName is null)
        {
            throw new InvalidOperationException(
                "Azure Blob image storage requires CATALOG_BLOB_SERVICE_ENDPOINT and CATALOG_BLOB_CONTAINER.");
        }

        var credential = new DefaultAzureCredential(
            new DefaultAzureCredentialOptions
            {
                ManagedIdentityClientId = options.WorkloadIdentityClientId,
            });
        _container = new BlobServiceClient(
                new Uri(options.BlobServiceEndpoint),
                credential)
            .GetBlobContainerClient(options.BlobContainerName);
    }

    public string GetImageUrl(string fileName) => $"/images/{fileName}";

    public async Task<ReadOnlyMemory<byte>?> ReadAsync(
        string fileName,
        CancellationToken cancellationToken)
    {
        // The canonical-key check is the traversal control, and it has to run here
        // too. ImageSecurityTests only exercises the static validator through
        // LocalImageStore, so a blob store that skipped this would keep the whole
        // suite green while accepting keys the local store rejects.
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
        catch (RequestFailedException exception)
            when (exception.Status == StatusCodes.Status404NotFound)
        {
            return null;
        }
    }
}
