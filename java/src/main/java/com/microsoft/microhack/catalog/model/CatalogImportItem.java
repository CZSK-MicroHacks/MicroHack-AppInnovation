package com.microsoft.microhack.catalog.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** Represents one untrusted record from a catalog import document. */
public record CatalogImportItem(
        @NotBlank String productId,
        @NotBlank @Size(min = 3, max = 80) String name,
        @NotBlank @Size(min = 20, max = 1200) String description,
        @NotBlank @Size(min = 2, max = 60) String category,
        @NotBlank String filename,
        @NotBlank @Size(min = 30, max = 260) String imagePrompt) {
}
