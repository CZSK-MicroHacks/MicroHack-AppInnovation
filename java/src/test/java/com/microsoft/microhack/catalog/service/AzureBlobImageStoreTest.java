package com.microsoft.microhack.catalog.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import org.junit.jupiter.api.Test;

/** Verifies that the Blob provider preserves canonical image-key behavior. */
class AzureBlobImageStoreTest {

    @Test
    void rejectsNoncanonicalKeysBeforeBlobAccess() throws Exception {
        BlobContainerClient container = mock(BlobContainerClient.class);
        AzureBlobImageStore store = new AzureBlobImageStore(container);

        assertThat(store.read("../catalog.png")).isEmpty();
        verifyNoInteractions(container);
    }

    @Test
    void returnsCanonicalBlobBytesUnchanged() throws Exception {
        String key = "10000000-0000-4000-8000-000000000001.png";
        byte[] expected = new byte[] {1, 2, 3};
        BlobContainerClient container = mock(BlobContainerClient.class);
        BlobClient blob = mock(BlobClient.class);
        when(container.getBlobClient(key)).thenReturn(blob);
        when(blob.downloadContent()).thenReturn(BinaryData.fromBytes(expected));

        assertThat(new AzureBlobImageStore(container).read(key)).contains(expected);
    }
}
