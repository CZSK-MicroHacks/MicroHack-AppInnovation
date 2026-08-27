"""Execute path-neutral HTTP and optional database acceptance checks."""

from __future__ import annotations

import json
import hashlib
import http.client
import posixpath
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from pydantic import ValidationError

from catalog_acceptance.database import (
    DatabaseState,
    delete_acceptance_fixture,
    fetch_database_state,
    verify_database,
)
from catalog_acceptance.manifest import category_slug, load_catalog, load_json, validate_seed
from catalog_acceptance.models.contracts import (
    AcceptanceReport,
    AcceptanceSubject,
    AcceptanceSettings,
    CatalogItem,
    CheckResult,
    CorpusCounts,
    HealthResponse,
    ImportResult,
    PerformanceResult,
    FULL_ACCEPTANCE_CHECKS,
)


RenderedFigure = tuple[str, str, str, str, str, str]


class CatalogHtmlParser(HTMLParser):
    """Collect stable catalog-card attributes without depending on quote style."""

    def __init__(self) -> None:
        """Initialize an empty parser result."""
        super().__init__()
        self.cards: list[RenderedFigure] = []
        self.details: list[RenderedFigure] = []
        self.has_empty_marker = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Collect contract attributes from rendered HTML elements."""
        attributes = dict(attrs)
        if "data-catalog-empty" in attributes:
            self.has_empty_marker = True
        figure_id = attributes.get("data-figure-id")
        name = attributes.get("data-figure-name")
        description = attributes.get("data-figure-description")
        category_name = attributes.get("data-category-name")
        category = attributes.get("data-category-slug")
        filename = attributes.get("data-image-filename")
        rendered = (
            figure_id,
            name,
            description,
            category_name,
            category,
            filename,
        )
        if all(value is not None for value in rendered):
            complete = tuple(rendered)
            if tag == "article":
                self.cards.append(complete)
            if attributes.get("data-figure-detail") == figure_id:
                self.details.append(complete)


def _parse_catalog_html(content: str) -> CatalogHtmlParser:
    """Parse stable catalog attributes from one HTML response."""
    parser = CatalogHtmlParser()
    parser.feed(content)
    return parser


def _result(
    name: str,
    passed: bool,
    success: str,
    failure: str,
    *,
    required: bool = True,
) -> CheckResult:
    """Build one passed or failed check result."""
    return CheckResult(
        name=name,
        status="passed" if passed else "failed",
        detail=success if passed else failure,
        required=required,
    )


def _description_only_term(items: list) -> str:
    """Choose a description token that is absent from every figure name."""
    names = " ".join(item.name.casefold() for item in items)
    for item in items:
        for word in re.findall(r"[A-Za-z]{8,}", item.description):
            if word.casefold() not in names:
                return word
    raise ValueError("canonical corpus has no description-only search term")


def _rendered_figure(item: CatalogItem) -> RenderedFigure:
    """Return the exact stable HTML identity for one catalog item."""
    return (
        str(item.product_id),
        item.name,
        item.description,
        item.category,
        category_slug(item.category),
        item.filename,
    )


def _has_content_type(response: httpx.Response, expected: str) -> bool:
    """Compare a response media type while allowing a charset parameter."""
    return response.headers.get("content-type", "").split(";", 1)[0].strip() == expected


def _raw_request_status(base_url: object, target: str) -> int:
    """Send an exact request target without client-side path normalization."""
    return _raw_request_probe(base_url, target)[0]


def _raw_request_probe(base_url: object, target: str) -> tuple[int, str, str]:
    """Send an exact request target and return ``(status, content-type, body sha256)``.

    The body fingerprint is what lets a caller tell *which* route answered. Status alone
    cannot: a gateway that resolves ``/images/../healthz`` before the application sees it
    produces a 200 that is indistinguishable, by status, from an application that served
    a traversed file.
    """
    parsed = urlsplit(str(base_url))
    if parsed.scheme not in ("http", "https") or parsed.hostname is None:
        raise ValueError("acceptance base URL must be HTTP or HTTPS")
    connection_type = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_type(parsed.hostname, parsed.port, timeout=10)
    base_path = parsed.path.rstrip("/")
    try:
        connection.request("GET", f"{base_path}{target}")
        response = connection.getresponse()
        body = response.read()
        content_type = (response.getheader("Content-Type") or "").split(";")[0].strip()
        return response.status, content_type, hashlib.sha256(body).hexdigest()
    finally:
        connection.close()


def _gateway_resolved_target(target: str) -> str:
    """Resolve ``target`` the way an HTTP gateway normalizes a request path.

    Percent-decoding, backslash folding and dot-segment removal, applied in the order a
    proxy applies them. Used only to predict *where* a normalizing gateway would have
    sent the request, so the outcome can be recognized rather than guessed at.
    """
    candidate = target
    for _ in range(3):
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    return posixpath.normpath(candidate.replace("\\", "/"))


def _classify_traversal(base_url: object, target: str) -> str:
    """Say what happened to an unsafe request target: the security question, not the status.

    Three outcomes, and only one of them is a failure:

    ``rejected``
        The application answered 404. The contract's original expectation.
    ``normalized-upstream``
        The response is byte-identical to a direct request for the path a gateway would
        have resolved ``target`` to, so the application never received the unsafe target
        at all. Nothing escaped the image store because nothing reached the image route.
    ``traversed``
        Anything else, including any response carrying image content. Conservative by
        construction: an outcome this function cannot explain is treated as a failure.

    Azure Container Apps fronts the workload with a gateway that performs dot-segment
    removal and backslash folding before the container is reached, and neither behaviour
    is configurable through the Container Apps API. Demanding a bare 404 therefore fails
    correct applications on the platform the workshop deploys to, and the only change an
    attendee can make that moves the number is deleting their own traversal guard. The
    contract is preserved here rather than relaxed: ``traversed`` still fails, and
    ``normalized-upstream`` is reported distinctly so a reader can always tell whether the
    application rejected the request or the platform resolved it upstream.

    A body fingerprint is the right discriminator only when the resolved target answers
    deterministically. Some do not: an authentication rejection commonly carries a
    correlation id, so two requests for the same path differ in the body and could never
    compare equal. Instability is therefore *proven* by probing the resolved target twice
    rather than assumed, and only then does the comparison fall back to status and content
    type. That fallback cannot mask an escape, because any response carrying image bytes
    has already been classified ``traversed`` above and a real traversal would answer with
    the status of the file it served rather than the status of the resolved route.
    """
    observed = _raw_request_probe(base_url, target)
    if observed[0] == 404:
        return "rejected"
    if observed[1].startswith("image/"):
        return "traversed"
    resolved = _gateway_resolved_target(target)
    if resolved == target:
        return "traversed"
    first = _raw_request_probe(base_url, resolved)
    if observed == first:
        return "normalized-upstream"
    second = _raw_request_probe(base_url, resolved)
    body_is_unstable = first[2] != second[2]
    if body_is_unstable and observed[:2] == first[:2] == second[:2]:
        return "normalized-upstream"
    return "traversed"


class AcceptanceRunner:
    """Run the frozen application contract against either implementation."""

    def __init__(self, settings: AcceptanceSettings) -> None:
        """Initialize a runner with validated settings."""
        self._settings = settings

    def run(self) -> AcceptanceReport:
        """Execute every configured check and return a machine-readable report."""
        started_at = datetime.now(timezone.utc)
        manifest = validate_seed(self._settings.data_directory)
        items = load_catalog(self._settings.data_directory)
        categories = load_json(self._settings.data_directory / "categories.json")
        checks: list[CheckResult] = []

        base_url = str(self._settings.base_url).rstrip("/")
        try:
            with httpx.Client(
                base_url=base_url,
                timeout=self._settings.timeout_seconds,
                follow_redirects=False,
            ) as client:
                checks.extend(self._check_health(client))
                checks.extend(self._check_catalog(client, items))
                checks.extend(self._check_details(client, items[0]))
                checks.append(self._check_images(client, items))
                if self._settings.verify_import:
                    checks.extend(self._check_import(client, items[0]))
                else:
                    checks.extend(
                        CheckResult(
                            name=name,
                            status="skipped",
                            detail="disabled by command-line option",
                            required=False,
                        )
                        for name in (
                            "import-new-category",
                            "idempotent-import",
                            "invalid-import",
                        )
                    )
                checks.extend(self._check_performance(client, items))
        except httpx.HTTPError as error:
            checks.append(
                CheckResult(
                    name="http-operation",
                    status="failed",
                    detail=f"HTTP verification failed: {type(error).__name__}",
                )
            )

        if (
            self._settings.database_kind
            and self._settings.database_host
            and self._settings.database_name
        ):
            try:
                username, password, access_token = self._database_credentials()
                verification = verify_database(
                    self._settings.database_kind,
                    self._settings.database_host,
                    self._settings.database_port,
                    self._settings.database_name,
                    username,
                    password,
                    self._settings.database_ssl_mode,
                    self._settings.database_trust_certificate,
                    self._settings.database_target,
                    items,
                    categories,
                    access_token,
                )
                checks.extend(
                    [
                        _result(
                            "database-corpus",
                            verification.figure_count == manifest.counts.figures
                            and verification.category_count
                            == manifest.counts.categories,
                            (
                                f"verified all fields for {verification.figure_count} "
                                f"figures and {verification.category_count} categories"
                            ),
                            "database corpus differs from the seed manifest",
                        ),
                        _result(
                            "database-schema",
                            True,
                            "application table columns, types, lengths, and nullability match",
                            "",
                        ),
                        _result(
                            "database-constraints",
                            True,
                            "keys, uniqueness, identity, foreign key, and checks match",
                            "",
                        ),
                        _result(
                            "database-indexes",
                            True,
                            "the exact application index set matches",
                            "",
                        ),
                        _result(
                            "database-migrations",
                            True,
                            "the required latest migration is applied",
                            "",
                        ),
                        _result(
                            "database-tls",
                            True,
                            verification.tls_detail,
                            "",
                        ),
                    ]
                )
            except (RuntimeError, ValueError) as error:
                checks.extend(
                    CheckResult(
                        name=name,
                        status="failed",
                        detail=f"database verification failed: {error}",
                    )
                    for name in FULL_ACCEPTANCE_CHECKS[-6:]
                )
        else:
            checks.extend(
                CheckResult(
                    name=name,
                    status="skipped",
                    detail="no complete database client configuration supplied",
                    required=self._settings.profile == "full",
                )
                for name in FULL_ACCEPTANCE_CHECKS[-6:]
            )

        if self._settings.profile == "full":
            indexed = {check.name: check for check in checks}
            checks = [
                indexed.get(
                    name,
                    CheckResult(
                        name=name,
                        status="failed",
                        detail="check did not run because an earlier operation failed",
                    ),
                )
                for name in FULL_ACCEPTANCE_CHECKS
            ]
        status = (
            "failed"
            if any(
                check.status == "failed"
                or (check.required and check.status == "skipped")
                for check in checks
            )
            else "passed"
        )
        return AcceptanceReport(
            profile=self._settings.profile,
            status=status,
            startedAt=started_at,
            finishedAt=datetime.now(timezone.utc),
            baseUrl=self._settings.base_url,
            databaseKind=self._settings.database_kind,
            databaseTarget=self._settings.database_target,
            subject=(
                AcceptanceSubject(
                    sourceCommit=self._settings.source_commit,
                    imageDigest=self._settings.image_digest,
                    revisionName=self._settings.revision_name,
                )
                if self._settings.source_commit
                and self._settings.image_digest
                and self._settings.revision_name
                else None
            ),
            corpus=CorpusCounts(
                figures=manifest.counts.figures,
                categories=manifest.counts.categories,
                images=manifest.counts.images,
            ),
            checks=checks,
        )

    def _check_health(self, client: httpx.Client) -> list[CheckResult]:
        """Check process liveness and database/import readiness semantics."""
        results: list[CheckResult] = []
        for name, path, expected_status in (
            ("liveness", "/healthz", "healthy"),
            ("readiness", "/readyz", "ready"),
        ):
            response = client.get(path)
            try:
                payload = HealthResponse.model_validate_json(response.content)
                valid_payload = payload.status == expected_status
                if name == "readiness":
                    valid_payload = (
                        valid_payload
                        and payload.checks is not None
                        and payload.checks.get("database") == "ready"
                        and payload.checks.get("import") == "ready"
                    )
            except ValidationError:
                valid_payload = False
            passed = (
                response.status_code == 200
                and _has_content_type(response, "application/json")
                and valid_payload
            )
            results.append(
                _result(
                    name,
                    passed,
                    f"{path} returned {expected_status}",
                    f"{path} returned HTTP {response.status_code} or invalid JSON",
                )
            )
        return results

    def _check_catalog(
        self, client: httpx.Client, items: list[CatalogItem]
    ) -> list[CheckResult]:
        """Check ordering, case-insensitive name search, and category filtering."""
        expected_cards = sorted(_rendered_figure(item) for item in items)
        root_response = client.get("/")
        root_html = _parse_catalog_html(root_response.text)
        root_passed = (
            root_response.status_code == 200
            and _has_content_type(root_response, "text/html")
            and root_html.cards == expected_cards
        )

        sample = items[0]
        search_term = sample.name.swapcase()
        search_response = client.get("/", params={"search": search_term})
        search_html = _parse_catalog_html(search_response.text)
        expected_search = sorted(
            _rendered_figure(item)
            for item in items
            if search_term.casefold() in item.name.casefold()
        )
        search_passed = (
            search_response.status_code == 200
            and _has_content_type(search_response, "text/html")
            and search_html.cards == expected_search
        )

        description_term = _description_only_term(items)
        description_response = client.get("/", params={"search": description_term})
        description_html = _parse_catalog_html(description_response.text)
        description_passed = (
            description_response.status_code == 200
            and _has_content_type(description_response, "text/html")
            and description_html.has_empty_marker
            and not description_html.cards
        )

        slug = category_slug(sample.category)
        expected_category = sorted(
            _rendered_figure(item)
            for item in items
            if item.category.casefold() == sample.category.casefold()
        )
        slug_response = client.get("/", params={"category": slug})
        slug_html = _parse_catalog_html(slug_response.text)
        slug_passed = (
            slug_response.status_code == 200
            and _has_content_type(slug_response, "text/html")
            and slug_html.cards == expected_category
        )
        name_response = client.get(
            "/",
            params={"category": sample.category.swapcase()},
        )
        name_html = _parse_catalog_html(name_response.text)
        name_passed = (
            name_response.status_code == 200
            and _has_content_type(name_response, "text/html")
            and name_html.cards == expected_category
        )
        wildcard_passed = True
        for literal, category in (
            ("%", slug),
            ("_", sample.category.swapcase()),
        ):
            response = client.get(
                "/",
                params={"search": literal, "category": category},
            )
            rendered = _parse_catalog_html(response.text)
            expected = sorted(
                _rendered_figure(item)
                for item in items
                if literal.casefold() in item.name.casefold()
                and item.category.casefold() == sample.category.casefold()
            )
            wildcard_passed = (
                wildcard_passed
                and response.status_code == 200
                and _has_content_type(response, "text/html")
                and rendered.cards == expected
            )

        return [
            _result(
                "catalog-order-and-count",
                root_passed,
                f"root rendered all {len(expected_cards)} canonical cards in productId order",
                f"root rendered {len(root_html.cards)} unexpected or out-of-order cards",
            ),
            _result(
                "name-search",
                search_passed and wildcard_passed,
                "case-insensitive literal name search returned exact results",
                "name search or literal wildcard behavior returned unexpected results",
            ),
            _result(
                "name-only-search",
                description_passed,
                "a description-only term returned no figures",
                "search matched a description field",
            ),
            _result(
                "category-filter-slug",
                slug_passed,
                f"category slug {slug} returned the exact ordered result set",
                f"category slug {slug} returned an unexpected result set",
            ),
            _result(
                "category-filter-name",
                name_passed,
                "case-insensitive display-name filter returned the exact result set",
                "display-name category filter returned an unexpected result set",
            ),
        ]

    def _check_details(
        self, client: httpx.Client, sample: CatalogItem
    ) -> list[CheckResult]:
        """Check known, unknown, and malformed figure identifiers."""
        known = client.get(f"/figure/{sample.product_id}")
        known_html = _parse_catalog_html(known.text)
        known_passed = (
            known.status_code == 200
            and _has_content_type(known, "text/html")
            and known_html.details == [_rendered_figure(sample)]
        )
        unknown = client.get("/figure/ffffffff-ffff-4fff-8fff-ffffffffffff")
        malformed = client.get("/figure/not-a-uuid")
        noncanonical = client.get(f"/figure/{str(sample.product_id).upper()}")
        return [
            _result(
                "known-figure",
                known_passed,
                "known figure detail returned HTTP 200",
                f"known figure detail returned HTTP {known.status_code} or invalid HTML",
            ),
            _result(
                "unknown-figure",
                (
                    unknown.status_code == 404
                    and malformed.status_code == 404
                    and noncanonical.status_code == 404
                ),
                "unknown, malformed, and noncanonical figure IDs returned HTTP 404",
                (
                    f"unknown={unknown.status_code}, malformed={malformed.status_code}, "
                    f"noncanonical={noncanonical.status_code}"
                ),
            ),
        ]

    def _check_images(
        self, client: httpx.Client, items: list[CatalogItem]
    ) -> CheckResult:
        """Check canonical images, missing images, and encoded traversal attempts."""
        selected = items if self._settings.verify_all_images else items[:1]
        failures: list[str] = []
        for item in selected:
            response = client.get(f"/images/{item.filename}")
            expected_digest = hashlib.sha256(
                (self._settings.data_directory / "images" / item.filename).read_bytes()
            ).hexdigest()
            actual_digest = hashlib.sha256(response.content).hexdigest()
            if (
                response.status_code != 200
                or not _has_content_type(response, "image/png")
                or actual_digest != expected_digest
            ):
                failures.append(item.filename)

        unknown = client.get("/images/ffffffff-ffff-4fff-8fff-ffffffffffff.png")
        malformed = client.get("/images/not-a-uuid.png")
        traversal_paths = {
            "raw-forward-existing": "/images/../healthz",
            "raw-backslash-existing": "/images\\..\\healthz",
            "encoded-forward-existing": "/images/%2e%2e%2fhealthz",
            "encoded-backslash-existing": "/images/%2e%2e%5chealthz",
            "double-encoded-existing": "/images/%252e%252e%252fhealthz",
            "raw-route-alias": "/perftest\\catalog",
            "encoded-route-alias": "/perftest%5ccatalog",
        }
        traversal_outcomes = {
            name: _classify_traversal(self._settings.base_url, path)
            for name, path in traversal_paths.items()
        }
        traversed = sorted(
            name for name, outcome in traversal_outcomes.items() if outcome == "traversed"
        )
        passed = (
            not failures
            and unknown.status_code == 404
            and malformed.status_code == 404
            and not traversed
        )
        return _result(
            "image-storage",
            passed,
            f"verified {len(selected)} images plus 404 and traversal behavior",
            (
                f"invalid images={failures[:3]}, unknown={unknown.status_code}, "
                f"malformed={malformed.status_code}, traversed={traversed}, "
                f"traversal={traversal_outcomes}"
            ),
        )

    def _check_import(
        self, client: httpx.Client, sample: CatalogItem
    ) -> list[CheckResult]:
        """Check successful publication, idempotency, atomic failure, and reset."""
        fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
        new_item = CatalogItem.model_validate(load_json(fixture_root / "catalog.valid.json")[0])
        import_page = client.get("/import")
        import_page_passed = (
            import_page.status_code == 200
            and _has_content_type(import_page, "text/html")
        )
        new_payload = json.dumps(
            [new_item.model_dump(by_alias=True, mode="json")]
        ).encode()

        new_passed = False
        new_detail = "fresh import is only exercised by the full profile"
        duplicate_passed = False
        duplicate_status = "not run"
        if self._settings.profile == "full":
            baseline: DatabaseState | None = None
            reset_passed = False
            try:
                self._delete_fixture(new_item)
                baseline = self._database_state()
                imported = client.post(
                    "/import",
                    files={
                        "catalogFile": (
                            "catalog.json",
                            new_payload,
                            "application/json",
                        )
                    },
                    headers={"Accept": "application/json"},
                )
                import_result = ImportResult.model_validate_json(imported.content)
                detail = client.get(f"/figure/{new_item.product_id}")
                detail_html = _parse_catalog_html(detail.text)
                category = client.get(
                    "/",
                    params={"category": category_slug(new_item.category)},
                )
                category_html = _parse_catalog_html(category.text)
                published = self._database_state()
                expected_figure = (*_rendered_figure(new_item), "valid")
                expected_figures = tuple(sorted((*baseline.figures, expected_figure)))
                expected_categories = tuple(
                    sorted(
                        (
                            *baseline.categories,
                            (new_item.category, category_slug(new_item.category)),
                        )
                    )
                )
                new_passed = (
                    imported.status_code == 200
                    and _has_content_type(imported, "application/json")
                    and import_result.inserted == 1
                    and import_result.skipped == 0
                    and import_result.total == 1
                    and detail.status_code == 200
                    and _has_content_type(detail, "text/html")
                    and detail_html.details == [_rendered_figure(new_item)]
                    and category.status_code == 200
                    and _has_content_type(category, "text/html")
                    and category_html.cards == [_rendered_figure(new_item)]
                    and published.figures == expected_figures
                    and published.categories == expected_categories
                )

                duplicate = client.post(
                    "/import",
                    files={
                        "catalogFile": (
                            "catalog.json",
                            new_payload,
                            "application/json",
                        )
                    },
                    headers={"Accept": "application/json"},
                )
                duplicate_result = ImportResult.model_validate_json(duplicate.content)
                duplicate_status = f"HTTP {duplicate.status_code}"
                duplicate_passed = (
                    duplicate.status_code == 200
                    and _has_content_type(duplicate, "application/json")
                    and duplicate_result.inserted == 0
                    and duplicate_result.skipped == 1
                    and duplicate_result.total == 1
                    and self._database_state() == published
                    and import_page_passed
                )
                new_detail = (
                    f"fresh figure {new_item.product_id} and category "
                    f"{new_item.category} published atomically"
                )
            except (RuntimeError, ValueError, ValidationError) as error:
                new_detail = f"fresh import verification failed: {error}"
            finally:
                try:
                    self._delete_fixture(new_item)
                    reset_passed = (
                        baseline is not None and self._database_state() == baseline
                    )
                except (RuntimeError, ValueError):
                    reset_passed = False
            new_passed = new_passed and reset_passed
            if not reset_passed:
                new_detail = f"{new_detail}; deterministic fixture reset failed"
        else:
            duplicate_payload = json.dumps(
                [sample.model_dump(by_alias=True, mode="json")]
            ).encode()
            duplicate = client.post(
                "/import",
                files={
                    "catalogFile": (
                        "catalog.json",
                        duplicate_payload,
                        "application/json",
                    )
                },
                headers={"Accept": "application/json"},
            )
            try:
                duplicate_result = ImportResult.model_validate_json(duplicate.content)
                duplicate_status = f"HTTP {duplicate.status_code}"
                duplicate_passed = (
                    duplicate.status_code == 200
                    and _has_content_type(duplicate, "application/json")
                    and duplicate_result.inserted == 0
                    and duplicate_result.skipped == 1
                    and duplicate_result.total == 1
                    and import_page_passed
                )
            except ValidationError:
                duplicate_passed = False

        invalid_path = fixture_root / "catalog.invalid-empty-slug.json"
        invalid_payload = invalid_path.read_bytes()
        invalid_records = load_json(invalid_path)
        invalid_ids = [record["productId"] for record in invalid_records]
        invalid_baseline: DatabaseState | None = None
        if self._settings.profile == "full":
            for record in invalid_records:
                self._delete_fixture_record(record)
            invalid_baseline = self._database_state()
        before_statuses = [
            client.get(f"/figure/{candidate_id}").status_code
            for candidate_id in invalid_ids
        ]
        invalid = client.post(
            "/import",
            files={"catalogFile": ("catalog.json", invalid_payload, "application/json")},
            headers={"Accept": "application/json"},
        )
        after_statuses = [
            client.get(f"/figure/{candidate_id}").status_code
            for candidate_id in invalid_ids
        ]
        invalid_database_unchanged = True
        if self._settings.profile == "full":
            invalid_database_unchanged = self._database_state() == invalid_baseline
            for record in invalid_records:
                self._delete_fixture_record(record)
        atomic_failure_passed = (
            all(status == 404 for status in before_statuses)
            and invalid.status_code == 400
            and all(status == 404 for status in after_statuses)
            and invalid_database_unchanged
        )
        return [
            CheckResult(
                name="import-new-category",
                status=(
                    "passed"
                    if new_passed
                    else "failed"
                    if self._settings.profile == "full"
                    else "skipped"
                ),
                detail=new_detail,
                required=self._settings.profile == "full",
            ),
            _result(
                "idempotent-import",
                duplicate_passed,
                "duplicate import skipped the existing figure",
                f"duplicate import returned {duplicate_status} or changed persistence",
            ),
            _result(
                "invalid-import",
                atomic_failure_passed,
                "mixed valid/invalid import returned HTTP 400 with no API or database publication",
                (
                    f"before={before_statuses}, import={invalid.status_code}, "
                    f"after={after_statuses}, databaseUnchanged={invalid_database_unchanged}"
                ),
            ),
        ]

    def _database_state(self) -> DatabaseState:
        """Read database state from the complete validated full-profile configuration."""
        settings = self._settings
        if (
            settings.database_kind is None
            or settings.database_host is None
            or settings.database_name is None
        ):
            raise ValueError("complete database configuration is required")
        username, password, access_token = self._database_credentials()
        return fetch_database_state(
            settings.database_kind,
            settings.database_host,
            settings.database_port,
            settings.database_name,
            username,
            password,
            settings.database_ssl_mode,
            settings.database_trust_certificate,
            settings.database_target,
            access_token,
        )

    def _database_credentials(self) -> tuple[str | None, str | None, str | None]:
        """Return the one validated database authentication mode."""
        settings = self._settings
        return (
            settings.database_username,
            (
                settings.database_password.get_secret_value()
                if settings.database_password
                else None
            ),
            (
                settings.database_access_token.get_secret_value()
                if settings.database_access_token
                else None
            ),
        )

    def _delete_fixture(self, item: CatalogItem) -> None:
        """Reset one typed item from the acceptance-owned identity range."""
        self._delete_fixture_record(
            {
                "productId": str(item.product_id),
                "category": item.category,
            }
        )

    def _delete_fixture_record(self, record: dict) -> None:
        """Reset one fixture record without touching canonical corpus identities."""
        settings = self._settings
        if (
            settings.database_kind is None
            or settings.database_host is None
            or settings.database_name is None
        ):
            raise ValueError("complete database configuration is required")
        username, password, access_token = self._database_credentials()
        delete_acceptance_fixture(
            settings.database_kind,
            settings.database_host,
            settings.database_port,
            settings.database_name,
            username,
            password,
            settings.database_ssl_mode,
            settings.database_trust_certificate,
            settings.database_target,
            record["productId"],
            record["category"],
            access_token,
        )

    def _check_performance(
        self, client: httpx.Client, items: list[CatalogItem]
    ) -> list[CheckResult]:
        """Check API-key enforcement and the bounded performance response."""
        missing = client.get("/perftest/catalog")
        invalid = client.get(
            "/perftest/catalog", headers={"x-api-key": "intentionally-wrong"}
        )
        authorized = client.get(
            "/perftest/catalog",
            headers={
                "x-api-key": self._settings.performance_api_key.get_secret_value()
            },
        )
        try:
            payload = PerformanceResult.model_validate_json(authorized.content)
            expected_dtos = [
                (
                    str(item.product_id),
                    item.name,
                    item.description,
                    item.category,
                    category_slug(item.category),
                    item.filename,
                )
                for item in sorted(items, key=lambda item: str(item.product_id))
            ]
            actual_dtos = [
                (
                    str(item.product_id),
                    item.name,
                    item.description,
                    item.category,
                    item.category_slug,
                    item.filename,
                )
                for item in payload.items
            ]
            response_passed = (
                authorized.status_code == 200
                and _has_content_type(authorized, "application/json")
                and payload.iterations == self._settings.expected_work_factor
                and actual_dtos == expected_dtos
            )
        except ValidationError:
            response_passed = False
        return [
            _result(
                "performance-authentication-missing",
                missing.status_code == 401
                and _has_content_type(missing, "application/json"),
                "missing performance API key returned HTTP 401",
                f"missing performance API key returned HTTP {missing.status_code}",
            ),
            _result(
                "performance-authentication-invalid",
                invalid.status_code == 401
                and _has_content_type(invalid, "application/json"),
                "invalid performance API key returned HTTP 401",
                f"invalid performance API key returned HTTP {invalid.status_code}",
            ),
            _result(
                "performance-contract",
                response_passed,
                (
                    f"performance endpoint returned {len(items)} canonical DTOs "
                    f"with work factor {self._settings.expected_work_factor}"
                ),
                f"performance endpoint returned HTTP {authorized.status_code} or invalid JSON",
            ),
        ]
