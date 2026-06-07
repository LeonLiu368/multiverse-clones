#!/usr/bin/env bash
# Boot Postgres + Mattermost (LOCALHOST ONLY), seed the workspace, deliver the agent's Slack
# token, then run the Slack Web API gateway on :80 as the container's main process.
set -uo pipefail

export PGDATA=/tmp/mm-pg
service postgresql start
sudo -u postgres sed -i "s/#port = 5432/port = 5433/" /etc/postgresql/14/main/postgresql.conf
sudo -u postgres sed -i "s/port = 5432/port = 5433/" /etc/postgresql/14/main/postgresql.conf
service postgresql restart
for i in $(seq 1 30); do sudo -u postgres pg_isready -h localhost -p 5433 && break; sleep 2; done
sudo -u postgres createuser --createdb --login mattermost -p 5433 || true
sudo -u postgres createdb -O mattermost mattermost -p 5433 || true
sudo -u postgres psql -p 5433 -c "ALTER USER mattermost PASSWORD 'mattermost';"

mkdir -p /mattermost/{logs,data,config,plugins}
chown -R mattermost:mattermost /mattermost/{logs,data,config,plugins}

# Mattermost bound to 127.0.0.1 — unreachable from the agent's container by design.
cat > /mattermost/config/config.json <<'EOF'
{
  "ServiceSettings": { "SiteURL":"http://localhost:8065","ListenAddress":"127.0.0.1:8065","EnableDeveloper":true,"EnableUserAccessTokens":true,"EnableLinkPreviews":false },
  "SqlSettings": { "DriverName":"postgres","DataSource":"postgres://mattermost:mattermost@localhost:5433/mattermost?sslmode=disable&connect_timeout=10" },
  "EmailSettings": { "SendEmailNotifications":false,"RequireEmailVerification":false,"EnableSignUpWithEmail":true },
  "PluginSettings": { "Enable":false },
  "LogSettings": { "EnableConsole":true,"ConsoleLevel":"ERROR","EnableFile":false },
  "FileSettings": { "EnableFileAttachments":false },
  "TeamSettings": { "EnableOpenServer":true }
}
EOF

cd /mattermost && ./bin/mattermost >/var/log/mm.log 2>&1 &
echo "🔄 waiting for Mattermost (localhost)..."
for i in $(seq 1 60); do curl -s http://localhost:8065/api/v4/system/ping >/dev/null 2>&1 && break; sleep 2; done

# Seed the chat workspace (admin/team/channels/posts) from the mounted data.
[ -f /data/mattermost/scraped.json ] && cp /data/mattermost/scraped.json /tmp/scraped.json
python3 /opt/seed.py || echo "⚠️ seed.py error"

# Per-task seed hook (optional): runs against the Slack GATEWAY once it is reachable, or does
# extra Mattermost-side setup. Invoked with the gateway not yet up, so it should use MM REST on
# localhost or be a no-op; most tasks seed purely via scraped.json above.
[ -x /usr/local/bin/task-seed.sh ] && bash /usr/local/bin/task-seed.sh || true

# The agent's Slack token is baked into the main image as env (xoxb-), the way a real Slack app
# is configured; the gateway validates that same token. Readiness is signalled simply by the
# gateway coming up on :80 (the compose healthcheck), which only happens after seeding here.
echo "🚀 starting Slack gateway on :80"
exec uvicorn slackgw.app:app --host 0.0.0.0 --port 80 --log-level warning --no-server-header
