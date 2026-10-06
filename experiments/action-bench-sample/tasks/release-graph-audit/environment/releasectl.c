#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <unistd.h>

#define AUDIT_PATH "/var/lib/releasectl/audit.jsonl"
#define FINALIZED_PATH "/var/lib/releasectl/submitted"
#define SUBMISSION_PATH "/app/release_handoff.json"

typedef struct {
    const char *id;
    const char *kind;
    const char *repo;
    int number;
    const char *title;
    const char *state;
    const char *labels;
    const char *owners;
    const char *severity;
    const char *checks;
    const char *blocking_reviewers;
    const char *paths;
    const char *depends_on;
    const char *blocks;
    const char *notes;
} Item;

static const Item ITEMS[] = {
    {"ISSUE-204","issue","platform-build",204,"Base image digest missing for web release","open","[\"release-blocker\",\"infra\"]","[\"platform-infra\"]","critical","[]","[]","[\"docker/base/web-runtime.Dockerfile\",\"ci/release-images.yml\"]","[]","[\"PR-411\",\"PR-518\"]","Both web portal and API gateway canaries consume this base image digest."},
    {"PR-411","pull_request","web-portal",411,"Ship install route retry wrapper","open","[\"release-blocker\",\"customer-visible\"]","[\"web-platform\"]","high","[{\"name\":\"e2e-install-route\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":false}]","[\"web-platform\"]","[\"apps/web/src/app/install/route.ts\",\"apps/web/src/lib/downloads.ts\"]","[\"ISSUE-204\"]","[]","Install route retry coverage is on the customer-visible release path."},
    {"PR-518","pull_request","api-gateway",518,"Route public downloads through region-aware edge","open","[\"release-blocker\"]","[\"edge-runtime\"]","high","[{\"name\":\"gateway-canary\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":false}]","[\"edge-runtime\"]","[\"gateway/routes/downloads.ts\",\"gateway/canary/config.yml\"]","[\"ISSUE-204\"]","[]","Canary covers the region-aware public download path for the train."},
    {"PR-233","pull_request","billing-ledger",233,"Backfill invoice settlement watermark","open","[\"release-blocker\",\"billing\"]","[\"billing\"]","critical","[{\"name\":\"migration-replay\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":false}]","[]","[\"migrations/20260607_settlement_watermark.sql\",\"ledger/replay.ts\"]","[]","[\"PR-377\"]","Migration replay fails on enterprise pooled invoices."},
    {"ISSUE-119","issue","mobile-shell",119,"App Store submission certificate expired","open","[\"release-blocker\",\"mobile\"]","[\"mobile\"]","high","[]","[]","[\"ios/certificates/release.mobileprovision\"]","[]","[]","Blocks iOS release upload even though code checks are green."},
    {"PR-377","pull_request","worker-scheduler",377,"Enable invoice settlement worker for pooled accounts","open","[\"train-watch\",\"billing\"]","[\"jobs-runtime\",\"billing\"]","medium","[{\"name\":\"worker-integration\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":false}]","[\"jobs-runtime\"]","[\"workers/invoiceSettlement.ts\",\"workers/schedules.ts\"]","[\"PR-233\"]","[\"ISSUE-451\"]","Settlement worker enablement is tied to the pooled-account rollout path."},
    {"ISSUE-451","issue","release-ops",451,"Assign owner for pooled settlement rollout","open","[\"rollout-gate\",\"billing\"]","[\"release-captains\",\"billing\"]","high","[{\"name\":\"owner-escalation-ready\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":false}]","[]","[\"runbooks/billing/settlement-rollout.md\"]","[\"PR-377\"]","[]","Manual production rollout gate for pooled settlement ownership."},
    {"PR-622","pull_request","search-indexer",622,"Refresh release search fixture cache","open","[\"release-blocker\",\"search\"]","[\"search\"]","medium","[{\"name\":\"fixture-refresh\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":true}]","[]","[\"search/fixtures/release-cache.ts\"]","[]","[]","Fixture refresh is queued against the search release lane."},
    {"PR-744","pull_request","web-portal",744,"Refresh install route screenshot fallback","open","[\"release-blocker\",\"customer-visible\"]","[\"web-platform\"]","high","[{\"name\":\"e2e-install-route\",\"conclusion\":\"failure\",\"required\":false,\"blocking\":false,\"waived\":false}]","[]","[\"apps/web/src/app/install/screenshots.ts\"]","[]","[]","Install route visual fallback is tracked in the same customer-visible lane."},
    {"ISSUE-809","issue","platform-build",809,"Backfill beta base image digest note","open","[\"release-blocker\",\"infra\"]","[\"platform-infra\"]","critical","[{\"name\":\"image-digest-note\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":true}]","[]","[\"docker/base/beta-web-runtime.Dockerfile\"]","[]","[]","Beta-lane digest note follows the same base-image ownership path."},
    {"PR-688","pull_request","billing-ledger",688,"Replay settlement dashboard counters","open","[\"release-blocker\",\"billing\"]","[\"billing\"]","high","[{\"name\":\"migration-replay\",\"conclusion\":\"failure\",\"required\":true,\"blocking\":true,\"waived\":true}]","[]","[\"ledger/dashboard/replayCounters.ts\"]","[]","[]","Settlement dashboard replay is queued beside the pooled billing rollout."},
    {"ISSUE-520","issue","mobile-shell",520,"Renew TestFlight provisioning reminder","open","[\"release-blocker\",\"mobile\"]","[\"mobile\"]","high","[]","[]","[\"ios/certificates/testflight.mobileprovision\"]","[]","[]","TestFlight provisioning reminder is owned by the same mobile release rotation."},
    {"PR-714","pull_request","api-gateway",714,"Tune download canary analytics sampling","open","[\"release-blocker\"]","[\"edge-runtime\"]","high","[{\"name\":\"gateway-canary\",\"conclusion\":\"failure\",\"required\":false,\"blocking\":false,\"waived\":false}]","[]","[\"gateway/canary/analytics.yml\"]","[]","[]","Analytics sampling rides beside the region-aware download canary."},
    {"PR-142","pull_request","docs-site",142,"Refresh changelog screenshots","open","[\"train-watch\"]","[\"docs\"]","low","[{\"name\":\"spellcheck\",\"conclusion\":\"success\"}]","[]","[\"docs/changelog.md\"]","[]","[]","Docs-only and not a blocker."},
    {"PR-620","pull_request","search-indexer",620,"Reduce index refresh batch size","open","[\"release-blocker\",\"performance\"]","[\"search\"]","high","[{\"name\":\"load-test\",\"conclusion\":\"failure\",\"required\":false,\"blocking\":false,\"waived\":false}]","[]","[\"indexer/batch.ts\"]","[]","[]","Performance follow-up shares the search release lane."},
    {"ISSUE-88","issue","marketing-site",88,"Hero image alt text typo","open","[\"accessibility\"]","[\"growth\"]","low","[]","[]","[\"site/pages/home.tsx\"]","[]","[]","Valid issue but not release blocking."},
    {"ISSUE-312","issue","web-portal",312,"Track post-train copy review","open","[\"release-blocker\",\"docs\"]","[\"growth\"]","low","[]","[]","[\"apps/web/copy/release-notes.md\"]","[]","[]","Copy review is linked to the train communication plan."},
    {"PR-299","pull_request","desktop-updater",299,"Bump beta channel copy","closed","[\"release-blocker\"]","[\"desktop\"]","high","[{\"name\":\"desktop-smoke\",\"conclusion\":\"failure\"}]","[\"desktop\"]","[\"updater/beta.ts\"]","[]","[]","Already closed; not an active blocker."},
    {"PR-501","pull_request","notifications",501,"Tune digest copy","open","[\"train-watch\"]","[\"notifications\"]","low","[{\"name\":\"unit\",\"conclusion\":\"success\",\"required\":true,\"blocking\":true,\"waived\":false}]","[]","[\"notifications/digestCopy.ts\"]","[]","[]","Digest copy touches train notifications."},
    {"ISSUE-73","issue","api-gateway",73,"Old canary alert did not auto-resolve","open","[\"ops-cleanup\"]","[\"edge-runtime\"]","medium","[]","[]","[\"alerts/gateway.yml\"]","[]","[]","Follow-up cleanup, not tied to the train."},
};

static void usage(void) {
    puts("Release train operations interface");
    puts("Usage:");
    puts("  releasectl docs");
    puts("  releasectl schema");
    puts("  releasectl list [--state open] [--label release-blocker]");
    puts("  releasectl get --id PR-123");
    puts("  releasectl checks --id PR-123");
    puts("  releasectl reviews --id PR-123");
    puts("  releasectl links --id PR-123");
    puts("  releasectl decisions --id PR-123");
    puts("  releasectl search --text billing");
    puts("  releasectl gates --train REL-884");
    puts("  releasectl submit --file <handoff.json>");
}

static const char *arg_value(int argc, char **argv, const char *flag) {
    for (int i = 2; i + 1 < argc; i++) {
        if (strcmp(argv[i], flag) == 0) {
            return argv[i + 1];
        }
    }
    return NULL;
}

static int audit_event_count(void) {
    FILE *fh = fopen(AUDIT_PATH, "r");
    if (fh == NULL) {
        return 0;
    }
    int count = 0;
    int ch;
    while ((ch = fgetc(fh)) != EOF) {
        if (ch == '\n') {
            count++;
        }
    }
    fclose(fh);
    return count;
}

static int append_audit(const char *line) {
    int fd = open(AUDIT_PATH, O_CREAT | O_APPEND | O_WRONLY, 0600);
    if (fd < 0) {
        fprintf(stderr, "releasectl: cannot write activity record: %s\n", strerror(errno));
        return 1;
    }
    dprintf(fd, "%s\n", line);
    close(fd);
    chmod(AUDIT_PATH, 0600);
    return 0;
}

static int audit(const char *tool, const char *args_json, int result_count) {
    int sequence = audit_event_count() + 1;
    char line[1024];
    snprintf(
        line,
        sizeof(line),
        "{\"tool\":\"%s\",\"arguments\":%s,\"result_count\":%d,\"sequence\":%d}",
        tool,
        args_json,
        result_count,
        sequence
    );
    if (append_audit(line) != 0) {
        return 1;
    }
    return 0;
}

static bool contains_ci(const char *haystack, const char *needle) {
    if (needle == NULL || *needle == '\0') {
        return true;
    }
    size_t n = strlen(needle);
    for (const char *h = haystack; *h; h++) {
        size_t i = 0;
        while (i < n && h[i] && tolower((unsigned char)h[i]) == tolower((unsigned char)needle[i])) {
            i++;
        }
        if (i == n) {
            return true;
        }
    }
    return false;
}

static bool item_matches_text(const Item *item, const char *text) {
    return contains_ci(item->id, text)
        || contains_ci(item->title, text)
        || contains_ci(item->repo, text)
        || contains_ci(item->labels, text)
        || contains_ci(item->paths, text);
}

static bool is_gate_item(const Item *item) {
    return contains_ci(item->labels, "rollout-gate");
}

static void print_summary(const Item *item) {
    printf(
        "{\"id\":\"%s\",\"kind\":\"%s\",\"repo\":\"%s\",\"number\":%d,\"title\":\"%s\",\"state\":\"%s\",\"labels\":%s}",
        item->id,
        item->kind,
        item->repo,
        item->number,
        item->title,
        item->state,
        item->labels
    );
}

static void print_full(const Item *item) {
    printf(
        "{\"id\":\"%s\",\"kind\":\"%s\",\"repo\":\"%s\",\"number\":%d,\"title\":\"%s\",\"state\":\"%s\",\"labels\":%s,\"owners\":%s,\"severity\":\"%s\",\"paths\":%s,\"notes\":\"%s\"}",
        item->id,
        item->kind,
        item->repo,
        item->number,
        item->title,
        item->state,
        item->labels,
        item->owners,
        item->severity,
        item->paths,
        item->notes
    );
}

static void print_checks(const Item *item) {
    printf("{\"id\":\"%s\",\"checks\":%s}", item->id, item->checks);
}

static void print_reviews(const Item *item) {
    printf("{\"id\":\"%s\",\"blocking_reviewers\":%s}", item->id, item->blocking_reviewers);
}

static void print_links(const Item *item) {
    printf("{\"id\":\"%s\",\"depends_on\":%s,\"blocks\":%s}", item->id, item->depends_on, item->blocks);
}

static void print_decision(const Item *item) {
    if (strcmp(item->id, "PR-622") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"waived\",\"waiver\":\"REL-WAIVER-17\",\"reason\":\"fixture refresh can ship after train cut without customer impact\"}", item->id);
        return;
    }
    if (strcmp(item->id, "PR-620") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"monitor\",\"waiver\":\"none\",\"reason\":\"load-test regression is non-blocking for this train but remains a performance follow-up\"}", item->id);
        return;
    }
    if (strcmp(item->id, "PR-744") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"monitor\",\"waiver\":\"none\",\"reason\":\"visual fallback is customer-visible but not a train stop; install-route backend coverage owns the blocker\"}", item->id);
        return;
    }
    if (strcmp(item->id, "ISSUE-809") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"waived\",\"waiver\":\"REL-WAIVER-24\",\"reason\":\"beta-lane digest note can land after REL-884 because stable images are unaffected\"}", item->id);
        return;
    }
    if (strcmp(item->id, "PR-688") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"waived\",\"waiver\":\"REL-WAIVER-25\",\"reason\":\"dashboard replay counters are explicitly waived for the same-day pooled settlement rollout\"}", item->id);
        return;
    }
    if (strcmp(item->id, "ISSUE-520") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"not_blocking\",\"waiver\":\"none\",\"reason\":\"TestFlight provisioning reminder does not affect App Store submission for REL-884\"}", item->id);
        return;
    }
    if (strcmp(item->id, "PR-714") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"monitor\",\"waiver\":\"none\",\"reason\":\"analytics sampling can be monitored after the train; gateway-canary failure is non-blocking here\"}", item->id);
        return;
    }
    if (strcmp(item->id, "ISSUE-312") == 0) {
        printf("{\"id\":\"%s\",\"release_decision\":\"not_blocking\",\"waiver\":\"none\",\"reason\":\"copy review moved to post-train communications follow-up\"}", item->id);
        return;
    }
    printf("{\"id\":\"%s\",\"release_decision\":\"blocking\",\"waiver\":\"none\",\"reason\":\"no active waiver or non-blocking release-manager decision\"}", item->id);
}

static int cmd_docs(void) {
    int rc = audit("docs", "{}", 1);
    if (rc != 0) {
        return rc;
    }
    puts("Release Train Notes");
    puts("");
    puts("The release room uses the current item graph to decide which owners need a same-day escalation.");
    puts("Start from active work tied to the train, then check detailed item records before naming a blocker.");
    puts("");
    puts("Escalate items that would stop the train from moving, especially when they involve:");
    puts("- release labels on customer-visible or critical paths");
    puts("- failed checks that block merge or deployment");
    puts("- missing required owner approvals");
    puts("- dependency links to other unresolved train work");
    puts("- high-severity operational issues");
    puts("");
    puts("Do not spend release-room time on closed items, docs-only follow-ups, unrelated maintenance work,");
    puts("or low-severity changes whose checks have already passed.");
    puts("");
    puts("The list view is only a triage index. Use releasectl list --state open for broad discovery, then releasectl get --id <ID>");
    puts("for items that need owner-ready evidence. Checks, review blockers, dependency links, and release-manager decisions");
    puts("are separate release-room surfaces.");
    puts("Release rollout gates are tracked separately from the PR/issue triage list. Use releasectl gates --train REL-884");
    puts("before finalizing the unblock plan.");
    return 0;
}

static int cmd_schema(void) {
    int rc = audit("schema", "{}", 1);
    if (rc != 0) {
        return rc;
    }
    puts("Release handoff submission schema:");
    puts("{");
    puts("  \"blockers\": [");
    puts("    {");
    puts("      \"id\": \"PR-123 or ISSUE-123\",");
    puts("      \"repo\": \"repository name\",");
    puts("      \"number\": 123,");
    puts("      \"kind\": \"pull_request or issue\",");
    puts("      \"title\": \"item title\",");
    puts("      \"owners\": [\"team or person responsible\"],");
    puts("      \"evidence\": [\"owner-ready reason this blocks the train\"],");
    puts("      \"recommended_rank\": 1");
    puts("    }");
    puts("  ],");
    puts("  \"unblock_order\": [\"IDs in dependency-safe order\"],");
    puts("  \"handoff_note\": \"short release-captain summary\"");
    puts("}");
    return 0;
}

static int cmd_list(int argc, char **argv) {
    const char *state = arg_value(argc, argv, "--state");
    const char *label = arg_value(argc, argv, "--label");
    int count = 0;
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (is_gate_item(&ITEMS[i])) {
            continue;
        }
        if (state != NULL && strcmp(ITEMS[i].state, state) != 0) {
            continue;
        }
        if (label != NULL && !contains_ci(ITEMS[i].labels, label)) {
            continue;
        }
        count++;
    }
    char args[256];
    snprintf(args, sizeof(args), "{\"state\":%s,\"label\":%s}", state ? "\"open\"" : "null", label ? "\"filtered\"" : "null");
    int rc = audit("list", args, count);
    if (rc != 0) {
        return rc;
    }
    puts("{\"ok\":true,\"items\":[");
    int emitted = 0;
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (is_gate_item(&ITEMS[i])) {
            continue;
        }
        if (state != NULL && strcmp(ITEMS[i].state, state) != 0) {
            continue;
        }
        if (label != NULL && !contains_ci(ITEMS[i].labels, label)) {
            continue;
        }
        if (emitted++) {
            puts(",");
        }
        print_summary(&ITEMS[i]);
    }
    puts("]}");
    return 0;
}

static int cmd_get(int argc, char **argv) {
    const char *id = arg_value(argc, argv, "--id");
    if (id == NULL) {
        printf("{\"ok\":false,\"error\":\"get requires --id\"}\n");
        return 2;
    }
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (strcasecmp(ITEMS[i].id, id) == 0) {
            char args[128];
            snprintf(args, sizeof(args), "{\"id\":\"%s\"}", ITEMS[i].id);
            int rc = audit("get", args, 1);
            if (rc != 0) {
                return rc;
            }
            printf("{\"ok\":true,\"item\":");
            print_full(&ITEMS[i]);
            puts("}");
            return 0;
        }
    }
    audit("get", "{\"id\":\"unknown\"}", 0);
    printf("{\"ok\":false,\"error\":\"unknown id\"}\n");
    return 2;
}

static int cmd_checks(int argc, char **argv) {
    const char *id = arg_value(argc, argv, "--id");
    if (id == NULL) {
        printf("{\"ok\":false,\"error\":\"checks requires --id\"}\n");
        return 2;
    }
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (strcasecmp(ITEMS[i].id, id) == 0) {
            char args[128];
            snprintf(args, sizeof(args), "{\"id\":\"%s\"}", ITEMS[i].id);
            int rc = audit("checks", args, 1);
            if (rc != 0) {
                return rc;
            }
            printf("{\"ok\":true,\"status\":");
            print_checks(&ITEMS[i]);
            puts("}");
            return 0;
        }
    }
    audit("checks", "{\"id\":\"unknown\"}", 0);
    printf("{\"ok\":false,\"error\":\"unknown id\"}\n");
    return 2;
}

static int cmd_reviews(int argc, char **argv) {
    const char *id = arg_value(argc, argv, "--id");
    if (id == NULL) {
        printf("{\"ok\":false,\"error\":\"reviews requires --id\"}\n");
        return 2;
    }
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (strcasecmp(ITEMS[i].id, id) == 0) {
            char args[128];
            snprintf(args, sizeof(args), "{\"id\":\"%s\"}", ITEMS[i].id);
            int rc = audit("reviews", args, 1);
            if (rc != 0) {
                return rc;
            }
            printf("{\"ok\":true,\"status\":");
            print_reviews(&ITEMS[i]);
            puts("}");
            return 0;
        }
    }
    audit("reviews", "{\"id\":\"unknown\"}", 0);
    printf("{\"ok\":false,\"error\":\"unknown id\"}\n");
    return 2;
}

static int cmd_links(int argc, char **argv) {
    const char *id = arg_value(argc, argv, "--id");
    if (id == NULL) {
        printf("{\"ok\":false,\"error\":\"links requires --id\"}\n");
        return 2;
    }
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (strcasecmp(ITEMS[i].id, id) == 0) {
            char args[128];
            snprintf(args, sizeof(args), "{\"id\":\"%s\"}", ITEMS[i].id);
            int rc = audit("links", args, 1);
            if (rc != 0) {
                return rc;
            }
            printf("{\"ok\":true,\"links\":");
            print_links(&ITEMS[i]);
            puts("}");
            return 0;
        }
    }
    audit("links", "{\"id\":\"unknown\"}", 0);
    printf("{\"ok\":false,\"error\":\"unknown id\"}\n");
    return 2;
}

static int cmd_decisions(int argc, char **argv) {
    const char *id = arg_value(argc, argv, "--id");
    if (id == NULL) {
        printf("{\"ok\":false,\"error\":\"decisions requires --id\"}\n");
        return 2;
    }
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (strcasecmp(ITEMS[i].id, id) == 0) {
            char args[128];
            snprintf(args, sizeof(args), "{\"id\":\"%s\"}", ITEMS[i].id);
            int rc = audit("decisions", args, 1);
            if (rc != 0) {
                return rc;
            }
            printf("{\"ok\":true,\"decision\":");
            print_decision(&ITEMS[i]);
            puts("}");
            return 0;
        }
    }
    audit("decisions", "{\"id\":\"unknown\"}", 0);
    printf("{\"ok\":false,\"error\":\"unknown id\"}\n");
    return 2;
}

static int cmd_search(int argc, char **argv) {
    const char *text = arg_value(argc, argv, "--text");
    if (text == NULL) {
        printf("{\"ok\":false,\"error\":\"search requires --text\"}\n");
        return 2;
    }
    int count = 0;
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (is_gate_item(&ITEMS[i])) {
            continue;
        }
        if (item_matches_text(&ITEMS[i], text)) {
            count++;
        }
    }
    int rc = audit("search", "{\"text\":\"query\"}", count);
    if (rc != 0) {
        return rc;
    }
    puts("{\"ok\":true,\"items\":[");
    int emitted = 0;
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (is_gate_item(&ITEMS[i])) {
            continue;
        }
        if (!item_matches_text(&ITEMS[i], text)) {
            continue;
        }
        if (emitted++) {
            puts(",");
        }
        print_summary(&ITEMS[i]);
    }
    puts("]}");
    return 0;
}

static int cmd_gates(int argc, char **argv) {
    const char *train = arg_value(argc, argv, "--train");
    if (train == NULL || strcmp(train, "REL-884") != 0) {
        printf("{\"ok\":false,\"error\":\"gates requires --train REL-884\"}\n");
        return 2;
    }
    int rc = audit("gates", "{\"train\":\"REL-884\"}", 1);
    if (rc != 0) {
        return rc;
    }
    puts("{\"ok\":true,\"gates\":[");
    for (size_t i = 0; i < sizeof(ITEMS) / sizeof(ITEMS[0]); i++) {
        if (strcmp(ITEMS[i].id, "ISSUE-451") == 0) {
            print_summary(&ITEMS[i]);
            break;
        }
    }
    puts("]}");
    return 0;
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
        printf("{\"ok\":false,\"error\":\"could not write handoff\"}\n");
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

static int cmd_submit(int argc, char **argv) {
    const char *file = arg_value(argc, argv, "--file");
    if (file == NULL) {
        printf("{\"ok\":false,\"error\":\"submit requires --file\"}\n");
        return 2;
    }
    if (!file_contains(file, "\"blockers\"") || !file_contains(file, "\"unblock_order\"") || !file_contains(file, "\"handoff_note\"")) {
        printf("{\"ok\":false,\"error\":\"handoff does not match releasectl schema\"}\n");
        return 2;
    }
    int rc = audit("submit", "{\"file\":\"handoff\"}", 1);
    if (rc != 0) {
        return rc;
    }
    rc = copy_file(file, SUBMISSION_PATH);
    if (rc != 0) {
        return rc;
    }
    FILE *fh = fopen(FINALIZED_PATH, "w");
    if (fh == NULL) {
        fprintf(stderr, "releasectl: cannot finalize handoff: %s\n", strerror(errno));
        return 1;
    }
    fputs("updated\n", fh);
    fclose(fh);
    chmod(FINALIZED_PATH, 0600);
    puts("{\"ok\":true,\"status\":\"handoff recorded\"}");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
        usage();
        return argc < 2 ? 2 : 0;
    }
    if (strcmp(argv[1], "docs") == 0) {
        return cmd_docs();
    }
    if (strcmp(argv[1], "schema") == 0) {
        return cmd_schema();
    }
    if (strcmp(argv[1], "list") == 0) {
        return cmd_list(argc, argv);
    }
    if (strcmp(argv[1], "get") == 0) {
        return cmd_get(argc, argv);
    }
    if (strcmp(argv[1], "checks") == 0) {
        return cmd_checks(argc, argv);
    }
    if (strcmp(argv[1], "reviews") == 0) {
        return cmd_reviews(argc, argv);
    }
    if (strcmp(argv[1], "links") == 0) {
        return cmd_links(argc, argv);
    }
    if (strcmp(argv[1], "decisions") == 0) {
        return cmd_decisions(argc, argv);
    }
    if (strcmp(argv[1], "search") == 0) {
        return cmd_search(argc, argv);
    }
    if (strcmp(argv[1], "gates") == 0) {
        return cmd_gates(argc, argv);
    }
    if (strcmp(argv[1], "submit") == 0) {
        return cmd_submit(argc, argv);
    }
    usage();
    return 2;
}
