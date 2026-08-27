"""Contract tests for the traversal outcome classifier.

The classifier decides whether an unsafe request target was rejected by the
application, resolved upstream by a normalizing gateway, or actually traversed.
Only the last is a failure, so a wrong answer in either direction is serious: a
false ``traversed`` fails correct work, and a false ``normalized-upstream`` would
hide a real escape.
"""

from __future__ import annotations

import posixpath
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator
from urllib.parse import unquote

import pytest

from catalog_acceptance.runner import _classify_traversal, _gateway_resolved_target


class _Handler(BaseHTTPRequestHandler):
    """Serve the minimum surface the classifier distinguishes between.

    The handler folds backslashes, percent-decodes and removes dot segments before
    routing, which models Azure Container Apps: an Envoy gateway normalizes the request
    target before the container ever sees it. Without that step the stub would be an
    application with no proxy in front of it, which is precisely the topology the
    classifier does *not* need to exist for.

    The normalization here is written out independently rather than reusing
    ``_gateway_resolved_target`` so the two are not circular; that helper is pinned
    separately against hardcoded expectations.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # noqa: D102 - silence test output
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _normalized_path(self) -> str:
        candidate = self.path
        for _ in range(3):
            decoded = unquote(candidate)
            if decoded == candidate:
                break
            candidate = decoded
        return posixpath.normpath(candidate.replace("\\", "/"))

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self._normalized_path()
        if path == "/healthz":
            self._send(200, "text/plain", b"ready")
        elif path.startswith("/images/") and path.endswith(".png"):
            self._send(200, "image/png", b"\x89PNG\r\n\x1a\n")
        elif path == "/perftest/catalog":
            # Deliberately non-deterministic: a correlation id in the body, which is
            # ordinary behaviour for an authentication rejection.
            body = f'{{"error":"unauthorized","correlationId":"{uuid.uuid4()}"}}'
            self._send(401, "application/json", body.encode())
        elif path == "/stable-401":
            self._send(401, "application/json", b'{"error":"unauthorized"}')
        else:
            self._send(404, "text/plain", b"not found")


@pytest.fixture()
def base_url() -> Iterator[str]:
    """Run the stub application on a loopback port for the duration of one test."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_resolution_folds_backslashes_and_dot_segments() -> None:
    """The predicted upstream target matches what a normalizing proxy would produce."""
    assert _gateway_resolved_target("/images/../healthz") == "/healthz"
    assert _gateway_resolved_target("/images/..\\healthz") == "/healthz"
    assert _gateway_resolved_target("/images/%2e%2e/healthz") == "/healthz"
    assert _gateway_resolved_target("/images/%252e%252e/healthz") == "/healthz"


def test_application_rejection_is_classified_as_rejected(base_url: str) -> None:
    """A 404 from the application is the contract's original expectation."""
    assert _classify_traversal(base_url, "/images/does-not-exist") == "rejected"


def test_image_content_is_always_traversed(base_url: str) -> None:
    """Any response carrying image bytes is a failure regardless of how it resolved."""
    assert _classify_traversal(base_url, "/images/escaped.png") == "traversed"


def test_upstream_normalization_is_recognized(base_url: str) -> None:
    """A response byte-identical to the resolved target never reached the image route."""
    assert _classify_traversal(base_url, "/images/../healthz") == "normalized-upstream"
    assert _classify_traversal(base_url, "/images/..\\healthz") == "normalized-upstream"


def test_stable_authentication_rejection_is_recognized(base_url: str) -> None:
    """A deterministic 401 at the resolved target compares equal and is recognized."""
    assert _classify_traversal(base_url, "/images/../stable-401") == "normalized-upstream"


def test_target_that_normalization_does_not_change_is_never_excused(
    base_url: str,
) -> None:
    """Only a target a gateway would have rewritten can be explained by normalization.

    If the request target survives normalization unchanged then nothing upstream
    rewrote it, so the application saw exactly what was sent and any non-404 answer is
    unexplained. Pins the conservative default against a future refactor that reaches
    the fallback comparison for a target that was never normalized at all.
    """
    assert _classify_traversal(base_url, "/stable-401") == "traversed"


def test_nondeterministic_body_at_resolved_target_is_not_reported_as_traversed(
    base_url: str,
) -> None:
    """A correlation id in the upstream response must not manufacture a failure.

    Regression guard for a defect in the classifier's first implementation: it compared
    a body fingerprint, so any resolved target whose body legitimately varies between
    two requests — an authentication rejection carrying a correlation id, for example —
    could never compare equal and was reported as ``traversed``. That fails correct work
    for a reason the attendee cannot see or influence, which is the exact failure mode
    the classifier exists to remove.
    """
    outcome = _classify_traversal(base_url, "/images/../perftest/catalog")
    assert outcome != "traversed"
    assert outcome == "normalized-upstream"
