package com.microsoft.microhack.catalog.web;

import com.microsoft.microhack.catalog.service.CatalogTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Emits standard HTTP server span attributes and one structured completion log. */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestTelemetryFilter extends OncePerRequestFilter {

    private static final Logger LOGGER = LoggerFactory.getLogger(RequestTelemetryFilter.class);
    private final CatalogTelemetry telemetry;

    public RequestTelemetryFilter(CatalogTelemetry telemetry) {
        this.telemetry = telemetry;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        Span span = telemetry.startSpan("http.server");
        span.setAttribute("http.request.method", request.getMethod());
        span.setAttribute("http.route", request.getRequestURI());
        span.setAttribute("server.address", request.getServerName());
        try (var scope = span.makeCurrent()) {
            filterChain.doFilter(request, response);
        } catch (IOException | ServletException | RuntimeException exception) {
            span.setStatus(StatusCode.ERROR);
            span.recordException(exception);
            throw exception;
        } finally {
            span.setAttribute("http.response.status_code", response.getStatus());
            CatalogTelemetry.log(LOGGER, "http.server.request", Map.of(
                    "http.request.method", request.getMethod(),
                    "http.route", request.getRequestURI(),
                    "http.response.status_code", response.getStatus()));
            span.end();
        }
    }
}
