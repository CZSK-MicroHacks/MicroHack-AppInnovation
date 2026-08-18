package com.microsoft.microhack.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.microsoft.microhack.catalog.service.CatalogDocumentParser;
import com.microsoft.microhack.catalog.service.CatalogImportValidationException;
import com.microsoft.microhack.catalog.service.CategorySlug;
import jakarta.validation.Validation;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/** Verifies shared normalization and canonical identity vectors without reinterpretation. */
class ConformanceVectorTest {

    private final ObjectMapper mapper = new ObjectMapper();
    private final CatalogDocumentParser parser = new CatalogDocumentParser(
            mapper,
            Validation.buildDefaultValidatorFactory().getValidator());

    @Test
    void categorySlugMatchesSharedVectors() throws Exception {
        JsonNode vectors = mapper.readTree(Files.readString(contract("normalization-vectors.json")));
        for (JsonNode vector : vectors.get("vectors")) {
            assertThat(CategorySlug.normalize(vector.get("input").asText()))
                    .isEqualTo(vector.get("expected").asText());
        }
        for (JsonNode vector : vectors.get("invalidVectors")) {
            assertThat(CategorySlug.normalize(vector.get("input").asText())).isEmpty();
        }
    }

    @Test
    void identityMatchesSharedVectors() throws Exception {
        JsonNode vectors = mapper.readTree(Files.readString(contract("identity-vectors.json")));
        for (JsonNode vector : vectors.get("vectors")) {
            String payload = mapper.writeValueAsString(new Object[] {new java.util.LinkedHashMap<>(
                    java.util.Map.of(
                            "productId", vector.get("productId").asText(),
                            "name", "Contract Figure",
                            "description",
                                    "A representative figure used to validate shared identity behavior.",
                            "category", "Contract Figures",
                            "filename", vector.get("filename").asText(),
                            "imagePrompt",
                                    "Photorealistic construction-toy figure on a clean studio background."))});
            if (vector.get("valid").asBoolean()) {
                assertThat(parser.parse(stream(payload))).hasSize(1);
            } else {
                assertThatThrownBy(() -> parser.parse(stream(payload)))
                        .isInstanceOf(CatalogImportValidationException.class);
            }
        }
    }

    @Test
    void completeDocumentRejectsValidPrefix() throws Exception {
        try (var input = Files.newInputStream(repositoryRoot()
                .resolve("tests/acceptance/fixtures/catalog.invalid.json"))) {
            assertThatThrownBy(() -> parser.parse(input))
                    .isInstanceOf(CatalogImportValidationException.class);
        }
    }

    private static ByteArrayInputStream stream(String value) {
        return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
    }

    private static Path contract(String filename) {
        return repositoryRoot().resolve("workshop/contracts").resolve(filename);
    }

    static Path repositoryRoot() {
        return Path.of("..").toAbsolutePath().normalize();
    }
}
