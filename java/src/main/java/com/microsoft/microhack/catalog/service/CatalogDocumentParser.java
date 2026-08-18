package com.microsoft.microhack.catalog.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.type.CollectionType;
import com.microsoft.microhack.catalog.model.CatalogImportItem;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/** Parses and validates complete catalog documents without publishing partial prefixes. */
@Component
public class CatalogDocumentParser {

    private static final Pattern CANONICAL_UUID = Pattern.compile(
            "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$");
    private final ObjectMapper objectMapper;
    private final Validator validator;

    public CatalogDocumentParser(ObjectMapper objectMapper, Validator validator) {
        this.objectMapper = objectMapper.copy()
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        this.validator = validator;
    }

    /** Returns only after every record and cross-record identity has been validated. */
    public List<ValidatedCatalogItem> parse(InputStream input) {
        List<CatalogImportItem> records = readDocument(input);
        if (records.isEmpty()) {
            throw new CatalogImportValidationException("catalog document must contain at least one record");
        }
        Map<String, String> namesToSlugs = new HashMap<>();
        Map<String, String> slugsToNames = new HashMap<>();
        return records.stream()
                .map(record -> validate(record, namesToSlugs, slugsToNames))
                .toList();
    }

    private List<CatalogImportItem> readDocument(InputStream input) {
        try {
            CollectionType listType = objectMapper.getTypeFactory()
                    .constructCollectionType(List.class, CatalogImportItem.class);
            return objectMapper.readValue(input, listType);
        } catch (JsonProcessingException exception) {
            throw new CatalogImportValidationException("catalog document is not valid JSON", exception);
        } catch (IOException exception) {
            throw new CatalogImportValidationException("catalog document could not be read", exception);
        }
    }

    private ValidatedCatalogItem validate(
            CatalogImportItem record,
            Map<String, String> namesToSlugs,
            Map<String, String> slugsToNames) {
        Set<ConstraintViolation<CatalogImportItem>> violations = validator.validate(record);
        if (!violations.isEmpty()) {
            throw new CatalogImportValidationException(
                    "catalog record violates " + violations.iterator().next().getPropertyPath());
        }
        if (!CANONICAL_UUID.matcher(record.productId()).matches()) {
            throw new CatalogImportValidationException(
                    "productId must be a canonical lowercase UUID");
        }
        UUID productId;
        try {
            productId = UUID.fromString(record.productId());
        } catch (IllegalArgumentException exception) {
            throw new CatalogImportValidationException("productId is not an RFC 4122 UUID", exception);
        }
        if (!record.productId().equals(productId.toString())) {
            throw new CatalogImportValidationException(
                    "productId must be a canonical lowercase UUID");
        }
        String expectedFilename = record.productId() + ".png";
        if (!expectedFilename.equals(record.filename())) {
            throw new CatalogImportValidationException(
                    "filename must equal productId plus .png");
        }
        String slug = CategorySlug.normalize(record.category());
        if (slug.isEmpty() || slug.length() > 64) {
            throw new CatalogImportValidationException(
                    "category must normalize to a non-empty slug of at most 64 characters");
        }
        String existingSlug = namesToSlugs.putIfAbsent(record.category(), slug);
        String existingName = slugsToNames.putIfAbsent(slug, record.category());
        if ((existingSlug != null && !existingSlug.equals(slug))
                || (existingName != null && !existingName.equals(record.category()))) {
            throw new CatalogImportValidationException(
                    "category display names and slugs must be unique");
        }
        return new ValidatedCatalogItem(
                productId,
                record.name(),
                record.description(),
                record.category(),
                slug,
                record.filename());
    }
}
