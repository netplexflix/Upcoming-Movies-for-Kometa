#!/bin/bash
set -e

# Clone repo if /app is empty
if [ -z "$(ls -A /app)" ]; then
    echo "[INFO] /app is empty, cloning repo..."
    git clone https://github.com/netplexflix/Upcoming-Movies-for-Kometa.git /app
fi

cd /app
git pull || echo "[WARN] git pull failed"

# Cron schedule (default 2AM)
CRON_SCHEDULE="${CRON:-0 2 * * *}"

# Run immediately if RUN_NOW=true
if [ "$RUN_NOW" = "true" ]; then
    echo "[INFO] RUN_NOW flag detected. Running UMFK.py immediately..."
    cd /app
    DOCKER=true /usr/local/bin/python /app/UMFK.py 2>&1 | tee -a /var/log/cron.log
fi

# Create cron job
echo "$CRON_SCHEDULE root cd /app && DOCKER=true /usr/local/bin/python /app/UMFK.py >> /var/log/cron.log 2>&1" > /etc/cron.d/umfk-cron
chmod 0644 /etc/cron.d/umfk-cron
crontab /etc/cron.d/umfk-cron

echo "[INFO] UMFK will also run according to cron schedule: $CRON_SCHEDULE"

# Ensure log file exists
touch /var/log/cron.log

# Start dcron in foreground to keep container alive
crond -f -l 2
