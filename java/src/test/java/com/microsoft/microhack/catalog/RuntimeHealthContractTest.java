package com.microsoft.microhack.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.microsoft.microhack.catalog.service.StartupState;
import com.microsoft.microhack.catalog.web.HealthController;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;

/** Emits the exact native JUnit health evidence names required by the handoff validator. */
class RuntimeHealthContractTest {

    @Test
    @DisplayName("Contract.Health.LivenessSurvivesDatabaseOutage")
    void livenessSurvivesDatabaseOutage() {
        HealthController controller = new HealthController(failingDatabase(), readyImport());

        assertThat(controller.liveness()).isEqualTo(Map.of("status", "healthy"));
    }

    @Test
    @DisplayName("Contract.Health.ReadinessFailsDuringDatabaseOutage")
    void readinessFailsDuringDatabaseOutage() {
        HealthController controller = new HealthController(failingDatabase(), readyImport());

        var response = controller.readiness();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isEqualTo(Map.of(
                "status", "not_ready",
                "checks", Map.of("database", "not_ready", "import", "ready")));
    }

    @Test
    @DisplayName("Contract.Health.ReadinessReportsImportFailure")
    void readinessReportsImportFailure() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject("SELECT 1", Integer.class)).thenReturn(1);
        StartupState startupState = new StartupState();
        startupState.failed();
        HealthController controller = new HealthController(jdbc, startupState);

        var response = controller.readiness();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isEqualTo(Map.of(
                "status", "not_ready",
                "checks", Map.of("database", "ready", "import", "failed")));
    }

    private static JdbcTemplate failingDatabase() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject("SELECT 1", Integer.class))
                .thenThrow(new DataAccessResourceFailureException("expected outage"));
        return jdbc;
    }

    private static StartupState readyImport() {
        StartupState startupState = new StartupState();
        startupState.ready();
        return startupState;
    }
}
