#!/bin/bash
# Mattermost (team edition) + embedded PostgreSQL, seeded for the incident-response task.
#
# Boot sequence (PG -> config -> server -> wait-for-ping) is adapted from APEX-SWE's
# docker-entrypoint-mattermost-lightweight.sh. The SEEDER is purpose-built for this task:
#   - creates one channel per distinct `channel` field in /data/mattermost/scraped.json
#   - accepts `author` as a plain string (not a Discord object)
#   - preserves original message timestamps
#   - no git-commit-time filtering (there is no paired code repo here)
# External contract relied on by the client + verifier:
#   admin  : admin@demo.local / AdminUser123!   (system admin)
#   team   : test-demo
#   channel: #incidents (+ #general, #engineering) seeded with the incident transcript
set -e

echo "🚀 Mattermost lightweight starting..."

export PGDATA="/tmp/mattermost-postgres-data"
export POSTGRES_USER="mattermost"
export POSTGRES_PASSWORD="mattermost"
export POSTGRES_DB="mattermost"

service postgresql start
sudo -u postgres sed -i "s/#port = 5432/port = 5433/" /etc/postgresql/14/main/postgresql.conf
sudo -u postgres sed -i "s/port = 5432/port = 5433/" /etc/postgresql/14/main/postgresql.conf
service postgresql restart

echo "🔄 Waiting for PostgreSQL on :5433..."
for i in $(seq 1 30); do
  if sudo -u postgres pg_isready -h localhost -p 5433; then echo "✅ PostgreSQL ready"; break; fi
  sleep 2
done

sudo -u postgres createuser --createdb --login "$POSTGRES_USER" -p 5433 || true
sudo -u postgres createdb -O "$POSTGRES_USER" "$POSTGRES_DB" -p 5433 || true
sudo -u postgres psql -p 5433 -c "ALTER USER $POSTGRES_USER PASSWORD '$POSTGRES_PASSWORD';"

mkdir -p /mattermost/{logs,data,config,plugins}
chmod -R 755 /mattermost/{data,logs,config,plugins}
chown -R mattermost:mattermost /mattermost/{data,logs,config,plugins}

cat > /mattermost/config/config.json << 'EOF'
{
  "ServiceSettings": {
    "SiteURL": "http://localhost:8065",
    "ListenAddress": ":8065",
    "EnableDeveloper": true,
    "EnableUserAccessTokens": true,
    "EnableLinkPreviews": false,
    "EnablePermalinkPreviews": false
  },
  "SqlSettings": {
    "DriverName": "postgres",
    "DataSource": "postgres://mattermost:mattermost@localhost:5433/mattermost?sslmode=disable&connect_timeout=10"
  },
  "EmailSettings": {
    "SendEmailNotifications": false,
    "RequireEmailVerification": false,
    "EnableSignUpWithEmail": true
  },
  "PluginSettings": { "Enable": false, "EnableUploads": false },
  "LogSettings": { "EnableConsole": true, "ConsoleLevel": "ERROR", "EnableFile": false },
  "FileSettings": { "EnableFileAttachments": false },
  "TeamSettings": { "MaxUsersPerTeam": 10000, "EnableOpenServer": true }
}
EOF

echo "🚀 Starting Mattermost server..."
cd /mattermost
./bin/mattermost &
MATTERMOST_PID=$!

echo "🔄 Waiting for Mattermost API..."
for i in $(seq 1 60); do
  if curl -s http://localhost:8065/api/v4/system/ping > /dev/null 2>&1; then echo "✅ API ready"; break; fi
  sleep 2
done

# ---- Seed -------------------------------------------------------------------
SCRAPED=""
for c in /data/mattermost/scraped.json /data/scraped.json; do
  [ -f "$c" ] && SCRAPED="$c" && break
done

if [ -n "$SCRAPED" ]; then
  echo "🔄 Seeding from $SCRAPED ..."
  cp "$SCRAPED" /tmp/scraped.json
  python3 /docker-seed.py || echo "⚠️ seed script reported an error (see above)"
else
  echo "ℹ️ No scraped.json found under /data/mattermost — creating admin + team only."
  python3 /docker-seed.py --no-messages || true
fi

echo "🎉 Mattermost init complete."
wait $MATTERMOST_PID
