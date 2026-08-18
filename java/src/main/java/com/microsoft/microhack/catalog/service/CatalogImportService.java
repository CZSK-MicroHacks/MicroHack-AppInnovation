package com.microsoft.microhack.catalog.service;

import com.microsoft.microhack.catalog.domain.Category;
import com.microsoft.microhack.catalog.domain.Figure;
import com.microsoft.microhack.catalog.model.ImportResult;
import com.microsoft.microhack.catalog.repository.CategoryRepository;
import com.microsoft.microhack.catalog.repository.FigureRepository;
import io.opentelemetry.api.trace.Span;
import java.io.InputStream;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Publishes a fully validated catalog document in one transaction. */
@Service
public class CatalogImportService {

    private static final Logger LOGGER = LoggerFactory.getLogger(CatalogImportService.class);
    private final CatalogDocumentParser parser;
    private final FigureRepository figures;
    private final CategoryRepository categories;
    private final CatalogTelemetry telemetry;

    public CatalogImportService(
            CatalogDocumentParser parser,
            FigureRepository figures,
            CategoryRepository categories,
            CatalogTelemetry telemetry) {
        this.parser = parser;
        this.figures = figures;
        this.categories = categories;
        this.telemetry = telemetry;
    }

    /** Validates the complete document before inserting any previously absent figure IDs. */
    @Transactional
    public ImportResult importDocument(InputStream input) {
        Span span = telemetry.startSpan("catalog.import");
        List<ValidatedCatalogItem> items = null;
        try (var scope = span.makeCurrent()) {
            items = parser.parse(input);
            int inserted = 0;
            int skipped = 0;
            Map<String, Category> categoryCache = new HashMap<>();
            for (ValidatedCatalogItem item : items) {
                if (figures.existsById(item.productId())) {
                    skipped++;
                    continue;
                }
                Category category = resolveCategory(item, categoryCache);
                OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
                figures.save(new Figure(
                        item.productId(),
                        item.name(),
                        item.description(),
                        category,
                        item.filename(),
                        now));
                inserted++;
            }
            figures.flush();
            span.setAttribute("catalog.import.inserted", inserted);
            span.setAttribute("catalog.import.skipped", skipped);
            span.setAttribute("catalog.import.rejected", 0);
            telemetry.recordImport(inserted, skipped, 0);
            CatalogTelemetry.log(LOGGER, "catalog.import.completed", Map.of(
                    "catalog.import.inserted", inserted,
                    "catalog.import.skipped", skipped));
            return new ImportResult(inserted, skipped, items.size());
        } catch (RuntimeException exception) {
            int rejected = 1;
            span.setAttribute("catalog.import.inserted", 0);
            span.setAttribute("catalog.import.skipped", 0);
            span.setAttribute("catalog.import.rejected", rejected);
            telemetry.recordImport(0, 0, rejected);
            CatalogTelemetry.failure(LOGGER, "catalog.import.failed", span, exception, Map.of(
                    "catalog.import.inserted", 0,
                    "catalog.import.skipped", 0,
                    "catalog.import.rejected", rejected));
            throw exception;
        } finally {
            span.end();
        }
    }

    private Category resolveCategory(
            ValidatedCatalogItem item,
            Map<String, Category> categoryCache) {
        Category cached = categoryCache.get(item.category());
        if (cached != null) {
            return cached;
        }
        Category byName = categories.findByName(item.category()).orElse(null);
        Category bySlug = categories.findBySlug(item.categorySlug()).orElse(null);
        if (byName != null && !byName.getSlug().equals(item.categorySlug())) {
            throw new CatalogImportValidationException("category name conflicts with its slug");
        }
        if (bySlug != null && !bySlug.getName().equals(item.category())) {
            throw new CatalogImportValidationException("category slug conflicts with its display name");
        }
        Category resolved = byName != null
                ? byName
                : bySlug != null
                        ? bySlug
                        : categories.save(new Category(item.category(), item.categorySlug()));
        categoryCache.put(item.category(), resolved);
        return resolved;
    }
}
