#!/bin/bash
# Creates a fake monitoring service for demo purposes
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script with sudo: sudo ./setup_demo_service.sh" >&2
  exit 1
fi

cat > /etc/systemd/system/ops-telemetry.service <<'EOF'
[Unit]
Description=OpsAgent Telemetry Monitor (Demo)
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c "while true; do sleep 60; done"
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ops-telemetry
systemctl start ops-telemetry
echo "ops-telemetry service installed and running"
