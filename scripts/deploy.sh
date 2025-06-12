#!/bin/bash
# RoluATM Complete Deployment Script
# Automates deployment of cloud API, kiosk backend, frontend, and monitoring

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLOUD_API_DIR="$PROJECT_ROOT/cloud-api"
KIOSK_DIR="$PROJECT_ROOT/kiosk-pi"
MONITORING_DIR="$PROJECT_ROOT/monitoring"

# Default values
CLOUD_API_URL=""
KIOSK_ID="kiosk-$(hostname)"
SERIAL_PORT="/dev/ttyACM0"
SKIP_TESTS=false
SKIP_MONITORING=false
PRODUCTION=false

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

show_help() {
    cat << EOF
RoluATM Deployment Script

Usage: $0 [OPTIONS]

OPTIONS:
    -c, --cloud-url URL     Cloud API URL (required for kiosk deployment)
    -k, --kiosk-id ID       Kiosk identifier (default: kiosk-\$(hostname))
    -s, --serial-port PORT  Serial port for coin mechanism (default: /dev/ttyACM0)
    -t, --skip-tests        Skip running tests
    -m, --skip-monitoring   Skip monitoring setup
    -p, --production        Production deployment mode
    -h, --help              Show this help message

EXAMPLES:
    # Deploy cloud API only
    $0

    # Deploy complete system
    $0 --cloud-url https://your-app.vercel.app --production

    # Deploy kiosk only
    $0 --cloud-url https://your-app.vercel.app --kiosk-id kiosk-001

EOF
}

check_dependencies() {
    log "Checking dependencies..."
    
    local missing=()
    
    # Check for required commands
    for cmd in git node npm python3 pip3; do
        if ! command -v $cmd &> /dev/null; then
            missing+=($cmd)
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing dependencies: ${missing[*]}"
    fi
    
    # Check Node.js version
    local node_version=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
    if [[ $node_version -lt 16 ]]; then
        error "Node.js 16+ required, found version $node_version"
    fi
    
    # Check Python version
    local python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"; then
        error "Python 3.8+ required, found version $python_version"
    fi
    
    log "✅ All dependencies satisfied"
}

deploy_cloud_api() {
    log "🌐 Deploying Cloud API to Vercel..."
    
    cd "$CLOUD_API_DIR"
    
    # Check if vercel CLI is installed
    if ! command -v vercel &> /dev/null; then
        info "Installing Vercel CLI..."
        npm install -g vercel
    fi
    
    # Deploy to Vercel
    if [[ $PRODUCTION == true ]]; then
        vercel --prod --yes
    else
        vercel --yes
    fi
    
    # Get deployment URL
    CLOUD_API_URL=$(vercel ls --scope=team 2>/dev/null | grep "$(basename "$CLOUD_API_DIR")" | head -1 | awk '{print $2}' | sed 's/.*\(https:\/\/[^[:space:]]*\).*/\1/')
    
    if [[ -z "$CLOUD_API_URL" ]]; then
        warn "Could not automatically detect Vercel URL"
        read -p "Please enter your Vercel deployment URL: " CLOUD_API_URL
    fi
    
    log "✅ Cloud API deployed to: $CLOUD_API_URL"
    cd "$PROJECT_ROOT"
}

setup_kiosk_environment() {
    log "⚙️  Setting up kiosk environment..."
    
    # Create backend environment
    cat > "$KIOSK_DIR/.env" << EOF
CLOUD_API_URL=$CLOUD_API_URL
KIOSK_ID=$KIOSK_ID
SERIAL_PORT=$SERIAL_PORT
LOG_LEVEL=INFO
LOG_FILE=/opt/roluatm/kiosk-pi/backend/logs/app.log
PROMETHEUS_PORT=9090
EOF

    # Create frontend environment
    cat > "$KIOSK_DIR/frontend/.env.local" << EOF
VITE_CLOUD_API_URL=$CLOUD_API_URL
VITE_KIOSK_ID=$KIOSK_ID
EOF
    
    log "✅ Environment files created"
}

install_kiosk_dependencies() {
    log "📦 Installing kiosk dependencies..."
    
    # Backend dependencies
    cd "$KIOSK_DIR/backend"
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    
    # Frontend dependencies
    cd "$KIOSK_DIR/frontend"
    npm install
    
    cd "$PROJECT_ROOT"
    log "✅ Dependencies installed"
}

build_frontend() {
    log "🏗️  Building frontend..."
    
    cd "$KIOSK_DIR/frontend"
    npm run build
    
    cd "$PROJECT_ROOT"
    log "✅ Frontend built"
}

run_tests() {
    if [[ $SKIP_TESTS == true ]]; then
        warn "Skipping tests"
        return
    fi
    
    log "🧪 Running tests..."
    
    # Backend tests
    info "Running backend tests..."
    cd "$KIOSK_DIR/backend"
    source venv/bin/activate
    python -m pytest tests/ -v || warn "Some backend tests failed"
    deactivate
    
    # Frontend tests
    info "Running frontend tests..."
    cd "$KIOSK_DIR/frontend"
    npm test -- --watchAll=false || warn "Some frontend tests failed"
    
    # E2E tests
    if [[ -n "$CLOUD_API_URL" ]]; then
        info "Running E2E tests..."
        cd "$PROJECT_ROOT"
        python3 tests/e2e_test.py "$CLOUD_API_URL" "http://localhost:5000" "http://localhost:3000" || warn "E2E tests failed"
    fi
    
    cd "$PROJECT_ROOT"
    log "✅ Tests completed"
}

setup_systemd_services() {
    log "🔧 Setting up systemd services..."
    
    # Backend service
    sudo tee /etc/systemd/system/roluatm-backend.service > /dev/null << EOF
[Unit]
Description=RoluATM Kiosk Backend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$KIOSK_DIR/backend
Environment=PATH=$KIOSK_DIR/backend/venv/bin
ExecStart=$KIOSK_DIR/backend/venv/bin/python app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    # Frontend service (using simple HTTP server)
    sudo tee /etc/systemd/system/roluatm-frontend.service > /dev/null << EOF
[Unit]
Description=RoluATM Kiosk Frontend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$KIOSK_DIR/frontend/dist
ExecStart=/usr/bin/python3 -m http.server 3000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    # Kiosk browser service
    if [[ -f "$KIOSK_DIR/systemd/kiosk-chromium.service" ]]; then
        sudo cp "$KIOSK_DIR/systemd/kiosk-chromium.service" /etc/systemd/system/
        sudo sed -i "s/http:\/\/localhost:3000/http:\/\/localhost:3000/g" /etc/systemd/system/kiosk-chromium.service
    fi
    
    sudo systemctl daemon-reload
    
    log "✅ Systemd services configured"
}

start_services() {
    log "🚀 Starting services..."
    
    sudo systemctl enable roluatm-backend roluatm-frontend
    sudo systemctl start roluatm-backend roluatm-frontend
    
    if [[ -f /etc/systemd/system/kiosk-chromium.service ]]; then
        sudo systemctl enable kiosk-chromium
        sudo systemctl start kiosk-chromium
    fi
    
    log "✅ Services started"
}

setup_monitoring() {
    if [[ $SKIP_MONITORING == true ]]; then
        warn "Skipping monitoring setup"
        return
    fi
    
    log "📊 Setting up monitoring..."
    
    if [[ -f "$MONITORING_DIR/setup_monitoring.sh" ]]; then
        bash "$MONITORING_DIR/setup_monitoring.sh"
    else
        warn "Monitoring setup script not found"
    fi
    
    log "✅ Monitoring configured"
}

verify_deployment() {
    log "🔍 Verifying deployment..."
    
    local errors=0
    
    # Check cloud API
    if [[ -n "$CLOUD_API_URL" ]]; then
        if curl -s -f "$CLOUD_API_URL/health" > /dev/null; then
            info "✅ Cloud API is responding"
        else
            error "❌ Cloud API is not responding"
            ((errors++))
        fi
    fi
    
    # Check kiosk backend
    if curl -s -f "http://localhost:5000/api/health" > /dev/null; then
        info "✅ Kiosk backend is responding"
    else
        warn "❌ Kiosk backend is not responding"
        ((errors++))
    fi
    
    # Check frontend
    if curl -s -f "http://localhost:3000" > /dev/null; then
        info "✅ Frontend is accessible"
    else
        warn "❌ Frontend is not accessible"
        ((errors++))
    fi
    
    # Check services status
    for service in roluatm-backend roluatm-frontend; do
        if systemctl is-active --quiet $service; then
            info "✅ $service is running"
        else
            warn "❌ $service is not running"
            ((errors++))
        fi
    done
    
    if [[ $errors -eq 0 ]]; then
        log "✅ All systems operational!"
    else
        warn "$errors issues detected. Check logs for details."
    fi
}

main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -c|--cloud-url)
                CLOUD_API_URL="$2"
                shift 2
                ;;
            -k|--kiosk-id)
                KIOSK_ID="$2"
                shift 2
                ;;
            -s|--serial-port)
                SERIAL_PORT="$2"
                shift 2
                ;;
            -t|--skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            -m|--skip-monitoring)
                SKIP_MONITORING=true
                shift
                ;;
            -p|--production)
                PRODUCTION=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done
    
    log "🚀 Starting RoluATM deployment..."
    log "Configuration:"
    log "  Cloud API URL: ${CLOUD_API_URL:-'Will be deployed'}"
    log "  Kiosk ID: $KIOSK_ID"
    log "  Serial Port: $SERIAL_PORT"
    log "  Production: $PRODUCTION"
    log "  Skip Tests: $SKIP_TESTS"
    log "  Skip Monitoring: $SKIP_MONITORING"
    
    # Main deployment flow
    check_dependencies
    
    # Deploy cloud API if URL not provided
    if [[ -z "$CLOUD_API_URL" ]]; then
        deploy_cloud_api
    fi
    
    # Kiosk deployment
    setup_kiosk_environment
    install_kiosk_dependencies
    build_frontend
    run_tests
    setup_systemd_services
    start_services
    setup_monitoring
    
    # Verification
    sleep 5  # Give services time to start
    verify_deployment
    
    log "🎉 RoluATM deployment completed!"
    log ""
    log "📊 Access URLs:"
    log "  Cloud API:    $CLOUD_API_URL"
    log "  Kiosk Backend: http://localhost:5000"
    log "  Frontend:     http://localhost:3000"
    log "  Monitoring:   http://localhost:3001 (if enabled)"
    log ""
    log "🔧 Management commands:"
    log "  View logs:    sudo journalctl -u roluatm-backend -f"
    log "  Restart:      sudo systemctl restart roluatm-backend roluatm-frontend"
    log "  Status:       sudo systemctl status roluatm-backend"
}

# Run main function
main "$@" 