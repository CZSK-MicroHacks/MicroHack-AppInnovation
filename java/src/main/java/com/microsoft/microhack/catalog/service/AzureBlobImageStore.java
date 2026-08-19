package com.microsoft.microhack.catalog.service;

import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.blob.models.BlobStorageException;
import com.microsoft.microhack.catalog.config.CatalogRuntimeOptions;
import java.io.IOException;
import java.util.Optional;

/** Reads canonical image objects from Blob Storage with the workload identity. */
public final class AzureBlobImageStore implements ImageStore {

    private final BlobContainerClient container;

    public AzureBlobImageStore(CatalogRuntimeOptions options) {
        this(new BlobServiceClientBuilder()
                .endpoint(options.blobServiceEndpoint().toString())
                .credential(new ManagedIdentityCredentialBuilder()
                        .clientId(options.workloadIdentityClientId())
                        .build())
                .buildClient()
                .getBlobContainerClient(options.blobContainerName()));
    }

    AzureBlobImageStore(BlobContainerClient container) {
        this.container = container;
    }

    @Override
    public Optional<byte[]> read(String key) throws IOException {
        if (!LocalImageStore.isCanonicalImageKey(key)) {
            return Optional.empty();
        }
        try {
            return Optional.of(container.getBlobClient(key).downloadContent().toBytes());
        } catch (BlobStorageException exception) {
            if (exception.getStatusCode() == 404) {
                return Optional.empty();
            }
            throw new IOException("Blob image read failed.", exception);
        }
    }
}
