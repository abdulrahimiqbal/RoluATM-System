#!/bin/bash
# RoluATM Monitoring Setup Script
# Sets up Grafana, Prometheus, and alerting for production monitoring

set -e

echo "🚀 Setting up RoluATM Monitoring Stack"
echo "=================================="

# Check if running on Raspberry Pi
if [[ ! -f /etc/rpi-issue ]]; then
    echo "⚠️  Warning: This script is designed for Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    echo "🐳 Installing Docker Compose..."
    sudo apt install -y python3-pip
    sudo pip3 install docker-compose
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Create monitoring directory structure
echo "📁 Creating monitoring directories..."
mkdir -p /opt/roluatm/monitoring/{grafana,prometheus,alertmanager}
mkdir -p /opt/roluatm/monitoring/grafana/{dashboards,provisioning}
mkdir -p /opt/roluatm/monitoring/prometheus/data
mkdir -p /opt/roluatm/monitoring/alertmanager/data

# Set permissions
sudo chown -R 472:472 /opt/roluatm/monitoring/grafana
sudo chown -R 65534:65534 /opt/roluatm/monitoring/prometheus/data
sudo chown -R 65534:65534 /opt/roluatm/monitoring/alertmanager/data

echo "✅ Monitoring directories created"

# Create Prometheus configuration
echo "⚙️  Creating Prometheus configuration..."
cat > /opt/roluatm/monitoring/prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "roluatm_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'roluatm-kiosk'
    static_configs:
      - targets: ['host.docker.internal:5000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'roluatm-cloud'
    static_configs:
      - targets: ['your-vercel-app.vercel.app']
    metrics_path: '/metrics'
    scrape_interval: 30s
    scheme: https
EOF

# Create alerting rules
echo "🚨 Creating alerting rules..."
cat > /opt/roluatm/monitoring/prometheus/roluatm_rules.yml << 'EOF'
groups:
  - name: roluatm_alerts
    rules:
      - alert: KioskDown
        expr: up{job="roluatm-kiosk"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "RoluATM Kiosk is down"
          description: "The RoluATM kiosk has been down for more than 1 minute"

      - alert: CloudAPIDown
        expr: up{job="roluatm-cloud"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "RoluATM Cloud API is down"
          description: "The RoluATM cloud API has been down for more than 2 minutes"

      - alert: HardwareError
        expr: roluatm_hardware_status == 0
        for: 30s
        labels:
          severity: warning
        annotations:
          summary: "Hardware error detected"
          description: "T-Flex coin mechanism is not responding"

      - alert: HighErrorRate
        expr: rate(roluatm_requests_total{status="error"}[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors per second"

      - alert: LowCoinInventory
        expr: roluatm_coin_inventory < 100
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Low coin inventory"
          description: "Coin inventory is below 100 quarters"
EOF

# Create Grafana dashboard
echo "📊 Creating Grafana dashboard..."
mkdir -p /opt/roluatm/monitoring/grafana/provisioning/{dashboards,datasources}

cat > /opt/roluatm/monitoring/grafana/provisioning/datasources/prometheus.yml << 'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF

cat > /opt/roluatm/monitoring/grafana/provisioning/dashboards/dashboard.yml << 'EOF'
apiVersion: 1
providers:
  - name: 'roluatm'
    orgId: 1
    folder: 'RoluATM'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: /etc/grafana/provisioning/dashboards
EOF

# Create Alertmanager configuration
echo "📢 Creating Alertmanager configuration..."
cat > /opt/roluatm/monitoring/alertmanager/alertmanager.yml << 'EOF'
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'roluatm@example.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'

receivers:
  - name: 'web.hook'
    email_configs:
      - to: 'admin@example.com'
        subject: 'RoluATM Alert: {{ .GroupLabels.alertname }}'
        body: |
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}
EOF

# Create Docker Compose file
echo "🐳 Creating Docker Compose configuration..."
cat > /opt/roluatm/monitoring/docker-compose.yml << 'EOF'
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus:/etc/prometheus
      - ./prometheus/data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=200h'
      - '--web.enable-lifecycle'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3001:3000"
    volumes:
      - ./grafana:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_USERS_ALLOW_SIGN_UP=false
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager:/etc/alertmanager
      - ./alertmanager/data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.ignored-mount-points'
      - '^/(sys|proc|dev|host|etc|rootfs/var/lib/docker/containers|rootfs/var/lib/docker/overlay2|rootfs/run/docker/netns|rootfs/var/lib/docker/aufs)($$|/)'
    restart: unless-stopped
EOF

# Create systemd service
echo "🔧 Creating systemd service..."
sudo tee /etc/systemd/system/roluatm-monitoring.service > /dev/null << 'EOF'
[Unit]
Description=RoluATM Monitoring Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/roluatm/monitoring
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable and start monitoring services
echo "🚀 Starting monitoring services..."
sudo systemctl daemon-reload
sudo systemctl enable roluatm-monitoring
sudo systemctl start roluatm-monitoring

echo "✅ Monitoring setup complete!"
echo ""
echo "📊 Access URLs:"
echo "   Grafana:     http://localhost:3001 (admin/admin123)"
echo "   Prometheus:  http://localhost:9090"
echo "   Alertmanager: http://localhost:9093"
echo ""
echo "🔧 Next steps:"
echo "1. Configure email settings in alertmanager.yml"
echo "2. Import RoluATM dashboard to Grafana"
echo "3. Set up notification channels"
echo "4. Test alerting rules"
echo ""
echo "🔍 Monitor status:"
echo "   sudo systemctl status roluatm-monitoring"
echo "   docker-compose -f /opt/roluatm/monitoring/docker-compose.yml logs" 