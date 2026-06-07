#!/usr/bin/env bash
# Single-container entrypoint: boot Postgres + Mattermost, seed the workspace,
# start the Slack gateway in the background, then keep the container alive for the agent.
# This is the only service in the compose — the agent runs in this same container.
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
echo "waiting for Mattermost..."
for i in $(seq 1 60); do curl -s http://localhost:8065/api/v4/system/ping >/dev/null 2>&1 && break; sleep 2; done

# Seed the chat workspace (admin/team/channels/posts) from the mounted data.
[ -f /data/mattermost/scraped.json ] && cp /data/mattermost/scraped.json /tmp/scraped.json
python3 /opt/seed.py || echo "seed.py error (non-fatal)"

# Per-task seed hooks (optional).
[ -x /usr/local/bin/task-seed.sh ] && bash /usr/local/bin/task-seed.sh || true
[ -f /data/mattermost/seed.sh ] && bash /data/mattermost/seed.sh || true

# Start the Slack gateway in the background.
echo "starting Slack gateway on :80"
uvicorn slackgw.app:app --host 0.0.0.0 --port 80 --log-level warning --no-server-header &

# Wait for the gateway to be reachable before signalling ready.
for i in $(seq 1 30); do curl -s http://localhost:80/api/auth.test >/dev/null 2>&1 && break; sleep 2; done
echo "gateway ready — agent tools available (SLACK_API_URL=$SLACK_API_URL)"

# Keep the container alive for the agent.
exec tail -f /dev/null
