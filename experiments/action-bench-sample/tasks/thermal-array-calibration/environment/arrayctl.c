#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define AUDIT_PATH "/var/lib/arrayctl/audit.jsonl"
#define STATE_PATH "/var/lib/arrayctl/state"
#define SUBMISSION_PATH "/app/calibration.json"
#define MEASUREMENT_LIMIT 13

typedef struct {
    const char *name;
    double scale;
    double offset;
    double stable_reported_stability;
} Probe;

static const Probe PROBES[] = {
    {"P1", 0.982, 0.00, 0.24},
    {"P2", 1.000, 0.46, 0.13},
    {"P3", 0.955, 0.00, 0.08},
    {"P4", 1.000, 0.00, 0.07},
    {"P5", 1.000, 1.20, 0.08},
};

static void usage(void) {
    puts("Thermal array controller");
    puts("Usage:");
    puts("  arrayctl manual");
    puts("  arrayctl history");
    puts("  arrayctl inventory");
    puts("  arrayctl criteria");
    puts("  arrayctl schema");
    puts("  arrayctl reference --setpoint ambient");
    puts("  arrayctl baseline --setpoint ambient");
    puts("  arrayctl measure --probe P1 --setpoint ambient --mode stable");
    puts("  arrayctl submit --file <calibration.json>");
}

static const Probe *find_probe(const char *name) {
    for (size_t i = 0; i < sizeof(PROBES) / sizeof(PROBES[0]); i++) {
        if (strcmp(PROBES[i].name, name) == 0) {
            return &PROBES[i];
        }
    }
    return NULL;
}

static const char *arg_value(int argc, char **argv, const char *flag) {
    for (int i = 2; i + 1 < argc; i++) {
        if (strcmp(argv[i], flag) == 0) {
            return argv[i + 1];
        }
    }
    return NULL;
}

static bool lookup_setpoint(const char *setpoint, double *actual) {
    if (strcmp(setpoint, "ambient") == 0 || strcmp(setpoint, "low") == 0) {
        *actual = 21.8;
        return true;
    }
    if (strcmp(setpoint, "mid") == 0) {
        *actual = 40.0;
        return true;
    }
    if (strcmp(setpoint, "hot") == 0 || strcmp(setpoint, "high") == 0) {
        *actual = 70.0;
        return true;
    }
    return false;
}

static bool lookup_bridge_offset(const char *setpoint, double *offset) {
    if (strcmp(setpoint, "ambient") == 0 || strcmp(setpoint, "low") == 0) {
        *offset = 0.42;
        return true;
    }
    if (strcmp(setpoint, "mid") == 0) {
        *offset = 0.86;
        return true;
    }
    if (strcmp(setpoint, "hot") == 0 || strcmp(setpoint, "high") == 0) {
        *offset = 1.58;
        return true;
    }
    return false;
}

static void load_state(int *measurements, int *submissions) {
    FILE *fh = fopen(STATE_PATH, "r");
    *measurements = 0;
    *submissions = 0;
    if (fh == NULL) {
        return;
    }
    if (fscanf(fh, "%d %d", measurements, submissions) != 2) {
        *measurements = 0;
        *submissions = 0;
    }
    fclose(fh);
}

static int save_state(int measurements, int submissions) {
    FILE *fh = fopen(STATE_PATH, "w");
    if (fh == NULL) {
        fprintf(stderr, "arrayctl: cannot write state: %s\n", strerror(errno));
        return 1;
    }
    fprintf(fh, "%d %d\n", measurements, submissions);
    fclose(fh);
    chmod(STATE_PATH, 0600);
    return 0;
}

static int append_audit(const char *line) {
    int fd = open(AUDIT_PATH, O_CREAT | O_APPEND | O_WRONLY, 0644);
    if (fd < 0) {
        fprintf(stderr, "arrayctl: cannot write activity record: %s\n", strerror(errno));
        return 1;
    }
    dprintf(fd, "%s\n", line);
    close(fd);
    chmod(AUDIT_PATH, 0644);
    return 0;
}

static double deterministic_noise(const char *probe, double temp, const char *mode) {
    char buf[128];
    snprintf(buf, sizeof(buf), "%s:%.2f:%s", probe, temp, mode);
    int seed = 0;
    for (char *p = buf; *p; p++) {
        seed += (unsigned char)*p;
    }
    return (((seed * 37) % 17) - 8) / 100.0;
}

static int copy_file(const char *src, const char *dst) {
    if (strcmp(src, dst) == 0) {
        chown(dst, 0, 0);
        chmod(dst, 0644);
        return 0;
    }
    FILE *in = fopen(src, "rb");
    if (in == NULL) {
        printf("{\"ok\":false,\"error\":\"could not read submission\"}\n");
        return 2;
    }
    FILE *out = fopen(dst, "wb");
    if (out == NULL) {
        fclose(in);
        printf("{\"ok\":false,\"error\":\"could not write calibration\"}\n");
        return 2;
    }
    char buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        fwrite(buf, 1, n, out);
    }
    fclose(in);
    fclose(out);
    chmod(dst, 0644);
    return 0;
}

static bool file_contains(const char *path, const char *needle) {
    FILE *fh = fopen(path, "rb");
    if (fh == NULL) {
        return false;
    }
    if (fseek(fh, 0, SEEK_END) != 0) {
        fclose(fh);
        return false;
    }
    long len = ftell(fh);
    if (len < 0 || len > 1048576) {
        fclose(fh);
        return false;
    }
    rewind(fh);
    char *buf = calloc((size_t)len + 1, 1);
    if (buf == NULL) {
        fclose(fh);
        return false;
    }
    size_t read_len = fread(buf, 1, (size_t)len, fh);
    fclose(fh);
    bool found = read_len == (size_t)len && strstr(buf, needle) != NULL;
    free(buf);
    return found;
}

static int cmd_manual(void) {
    puts("Thermal array manual");
    puts("- Probes: P1, P2, P3, P4, P5");
    puts("- inventory returns slot and role metadata for each probe");
    puts("- reference returns the certified dry-well temperature for ambient|mid|hot; setpoint names are labels, not exact temperatures");
    puts("- baseline returns the bridge/readout offset for the current setpoint");
    puts("- measure requires --probe, --setpoint ambient|mid|hot, and --mode stable|warmup");
    puts("- stable measurements are preferred for calibration");
    puts("- the bench has a 13-measurement same-day quota");
    puts("- run arrayctl criteria for trim thresholds");
    puts("- run arrayctl schema for the calibration submission format");
    return 0;
}

static int cmd_history(void) {
    if (append_audit("{\"tool\":\"history\",\"arguments\":{},\"result\":{\"status\":\"displayed\"}}") != 0) {
        return 1;
    }
    puts("Maintenance history for bench B");
    puts("- Last window: dry-well reference certificate revalidated; controller firmware unchanged.");
    puts("- Harness cleanup disturbed two probe channels and the readout bridge zero, but the paper slot labels were stale after the probe swap.");
    puts("- The post-maintenance smoke check saw mixed residuals near the corrective-trim threshold.");
    puts("- Current inventory and fresh measurements must drive targeted follow-up; do not rely on stale slot notes alone.");
    puts("- Warmup readings can move while the array settles; stable readings are the calibration source of truth.");
    puts("- A reference probe should have low residual error and low reported stability across the hot span.");
    return 0;
}

static int cmd_criteria(void) {
    if (append_audit("{\"tool\":\"criteria\",\"arguments\":{},\"result\":{\"status\":\"displayed\"}}") != 0) {
        return 1;
    }
    puts("Calibration criteria");
    puts("- subtract the bridge baseline for each setpoint before fitting probe-specific trims");
    puts("- classify a scale fault when a three-point stable fit has observed_scale <= 0.975 or >= 1.025");
    puts("- classify an offset fault when a three-point stable fit has |observed_offset_c| >= 0.80 and |observed_scale - 1.0| < 0.025");
    puts("- reference_probe must be reference_class true, stable across the measured span, and lower residual than the alternate reference candidate");
    puts("- values inside those trim thresholds are notes for maintenance, not same-day corrective faults");
    return 0;
}

static int cmd_inventory(void) {
    if (append_audit("{\"tool\":\"inventory\",\"arguments\":{},\"result\":{\"status\":\"displayed\"}}") != 0) {
        return 1;
    }
    puts("Bench B probe inventory");
    puts("- slot A: probe P1, role array, reference_class false");
    puts("- slot B: probe P2, role reference-candidate, reference_class true");
    puts("- slot C: probe P4, role reference-candidate, reference_class true");
    puts("- slot D: probe P3, role array, reference_class false");
    puts("- slot E: probe P5, role array, reference_class false");
    return 0;
}

static int cmd_schema(void) {
    puts("Calibration submission schema:");
    puts("{");
    puts("  \"scale_fault\": {\"probe\": \"P?\", \"observed_scale\": 0.0},");
    puts("  \"offset_fault\": {\"probe\": \"P?\", \"observed_offset_c\": 0.0},");
    puts("  \"reference_probe\": \"P?\",");
    puts("  \"notes\": \"technician-facing measurement rationale and final values\"");
    puts("}");
    return 0;
}

static int cmd_reference(int argc, char **argv) {
    const char *setpoint = arg_value(argc, argv, "--setpoint");
    if (setpoint == NULL) {
        printf("{\"ok\":false,\"error\":\"reference requires --setpoint\"}\n");
        return 2;
    }
    double actual = 0.0;
    if (!lookup_setpoint(setpoint, &actual)) {
        printf("{\"ok\":false,\"error\":\"unknown setpoint\"}\n");
        return 2;
    }
    char audit[512];
    snprintf(
        audit,
        sizeof(audit),
        "{\"tool\":\"reference\",\"arguments\":{\"setpoint\":\"%s\"},\"result\":{\"setpoint\":\"%s\",\"actual_temp_c\":%.3f,\"uncertainty_c\":0.030}}",
        setpoint,
        setpoint,
        actual
    );
    if (append_audit(audit) != 0) {
        return 1;
    }
    printf(
        "{\"ok\":true,\"result\":{\"setpoint\":\"%s\",\"actual_temp_c\":%.3f,\"uncertainty_c\":0.030}}\n",
        setpoint,
        actual
    );
    return 0;
}

static int cmd_baseline(int argc, char **argv) {
    const char *setpoint = arg_value(argc, argv, "--setpoint");
    if (setpoint == NULL) {
        printf("{\"ok\":false,\"error\":\"baseline requires --setpoint\"}\n");
        return 2;
    }
    double offset = 0.0;
    if (!lookup_bridge_offset(setpoint, &offset)) {
        printf("{\"ok\":false,\"error\":\"unknown setpoint\"}\n");
        return 2;
    }
    char audit[512];
    snprintf(
        audit,
        sizeof(audit),
        "{\"tool\":\"baseline\",\"arguments\":{\"setpoint\":\"%s\"},\"result\":{\"setpoint\":\"%s\",\"bridge_offset_c\":%.3f,\"apply\":\"subtract before fitting probe trims\"}}",
        setpoint,
        setpoint,
        offset
    );
    if (append_audit(audit) != 0) {
        return 1;
    }
    printf(
        "{\"ok\":true,\"result\":{\"setpoint\":\"%s\",\"bridge_offset_c\":%.3f,\"apply\":\"subtract before fitting probe trims\"}}\n",
        setpoint,
        offset
    );
    return 0;
}

static int cmd_measure(int argc, char **argv) {
    const char *probe_name = arg_value(argc, argv, "--probe");
    const char *setpoint = arg_value(argc, argv, "--setpoint");
    const char *mode = arg_value(argc, argv, "--mode");
    if (probe_name == NULL || setpoint == NULL || mode == NULL) {
        printf("{\"ok\":false,\"error\":\"measure requires --probe, --setpoint, and --mode\"}\n");
        return 2;
    }
    const Probe *probe = find_probe(probe_name);
    if (probe == NULL) {
        printf("{\"ok\":false,\"error\":\"unknown probe\"}\n");
        return 2;
    }
    if (strcmp(mode, "stable") != 0 && strcmp(mode, "warmup") != 0) {
        printf("{\"ok\":false,\"error\":\"unknown mode\"}\n");
        return 2;
    }
    double actual = 0.0;
    if (!lookup_setpoint(setpoint, &actual)) {
        printf("{\"ok\":false,\"error\":\"unknown setpoint\"}\n");
        return 2;
    }

    int measurements, submissions;
    load_state(&measurements, &submissions);
    if (measurements >= MEASUREMENT_LIMIT) {
        printf("{\"ok\":false,\"error\":\"measurement quota exhausted\",\"limit\":%d}\n", MEASUREMENT_LIMIT);
        return 2;
    }
    measurements += 1;
    if (save_state(measurements, submissions) != 0) {
        return 1;
    }

    double bridge_offset = 0.0;
    lookup_bridge_offset(setpoint, &bridge_offset);
    double reading = actual * probe->scale + probe->offset + bridge_offset + deterministic_noise(probe_name, actual, mode);
    if (strcmp(mode, "warmup") == 0) {
        reading += 0.12 * sin(actual / 9.0);
    }
    double stability = strcmp(mode, "stable") == 0 ? probe->stable_reported_stability : 0.18;

    char audit[1024];
    snprintf(
        audit,
        sizeof(audit),
        "{\"tool\":\"measure\",\"arguments\":{\"probe\":\"%s\",\"setpoint\":\"%s\",\"mode\":\"%s\"},\"result\":{\"probe\":\"%s\",\"setpoint\":\"%s\",\"mode\":\"%s\",\"reading_c\":%.3f,\"reported_stability_c\":%.2f}}",
        probe_name,
        setpoint,
        mode,
        probe_name,
        setpoint,
        mode,
        reading,
        stability
    );
    if (append_audit(audit) != 0) {
        return 1;
    }

    printf(
        "{\"ok\":true,\"measurements_remaining\":%d,\"result\":{\"probe\":\"%s\",\"setpoint\":\"%s\",\"mode\":\"%s\",\"reading_c\":%.3f,\"reported_stability_c\":%.2f}}\n",
        MEASUREMENT_LIMIT - measurements,
        probe_name,
        setpoint,
        mode,
        reading,
        stability
    );
    return 0;
}

static int cmd_submit(int argc, char **argv) {
    const char *file = arg_value(argc, argv, "--file");
    if (file == NULL) {
        printf("{\"ok\":false,\"error\":\"submit requires --file\"}\n");
        return 2;
    }
    if (!file_contains(file, "\"scale_fault\"") || !file_contains(file, "\"offset_fault\"") || !file_contains(file, "\"reference_probe\"") || !file_contains(file, "\"notes\"")) {
        printf("{\"ok\":false,\"error\":\"calibration does not match arrayctl schema\"}\n");
        return 2;
    }

    int measurements, submissions;
    load_state(&measurements, &submissions);
    if (submissions >= 1) {
        printf("{\"ok\":false,\"error\":\"calibration already submitted\"}\n");
        return 2;
    }
    int rc = copy_file(file, SUBMISSION_PATH);
    if (rc != 0) {
        return rc;
    }
    submissions += 1;
    if (save_state(measurements, submissions) != 0) {
        return 1;
    }
    if (append_audit("{\"tool\":\"submit\",\"arguments\":{\"file\":\"calibration\"},\"result\":{\"status\":\"accepted\"}}") != 0) {
        return 1;
    }
    puts("{\"ok\":true,\"status\":\"calibration accepted\"}");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
        usage();
        return argc < 2 ? 2 : 0;
    }
    if (strcmp(argv[1], "manual") == 0) {
        return cmd_manual();
    }
    if (strcmp(argv[1], "history") == 0) {
        return cmd_history();
    }
    if (strcmp(argv[1], "inventory") == 0) {
        return cmd_inventory();
    }
    if (strcmp(argv[1], "criteria") == 0) {
        return cmd_criteria();
    }
    if (strcmp(argv[1], "schema") == 0) {
        return cmd_schema();
    }
    if (strcmp(argv[1], "reference") == 0) {
        return cmd_reference(argc, argv);
    }
    if (strcmp(argv[1], "baseline") == 0) {
        return cmd_baseline(argc, argv);
    }
    if (strcmp(argv[1], "measure") == 0) {
        return cmd_measure(argc, argv);
    }
    if (strcmp(argv[1], "submit") == 0) {
        return cmd_submit(argc, argv);
    }
    usage();
    return 2;
}
