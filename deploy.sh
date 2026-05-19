#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# NEXUS Supply Chain Control Tower — Deployment Script
# Supports: local, docker, kubernetes, and cloud deployments
# Usage: ./scripts/deploy.sh [local|docker|k8s|staging|production]
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail
IFS=$'\n\t'

# ─── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Variables ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${1:-local}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/nexus_deploy_${TIMESTAMP}.log"

# ─── Logging ─────────────────────────────────────────────────────────
log()     { echo -e "${BOLD}[$(date '+%H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
success() { echo -e "${GREEN}${BOLD}✅ $*${NC}" | tee -a "$LOG_FILE"; }
warn()    { echo -e "${YELLOW}${BOLD}⚠️  $*${NC}" | tee -a "$LOG_FILE"; }
error()   { echo -e "${RED}${BOLD}❌ $*${NC}" | tee -a "$LOG_FILE" >&2; exit 1; }
info()    { echo -e "${CYAN}   $*${NC}" | tee -a "$LOG_FILE"; }
header()  { echo -e "\n${BLUE}${BOLD}══ $* ══${NC}\n" | tee -a "$LOG_FILE"; }

# ─── Banner ──────────────────────────────────────────────────────────
print_banner() {
  echo -e "${CYAN}${BOLD}"
  cat << 'EOF'
╔══════════════════════════════════════════════════════════╗
║         NEXUS Supply Chain Control Tower                 ║
║         Autonomous AI Deployment System v2.4             ║
╚══════════════════════════════════════════════════════════╝
EOF
  echo -e "${NC}"
}

# ─── Prerequisites Check ─────────────────────────────────────────────
check_prerequisites() {
  header "Checking Prerequisites"
  local missing=()

  for cmd in docker docker-compose python3 node npm git; do
    if command -v "$cmd" &>/dev/null; then
      success "$cmd: $(command -v $cmd)"
    else
      warn "Missing: $cmd"
      missing+=("$cmd")
    fi
  done

  if [[ "$ENVIRONMENT" == "k8s" || "$ENVIRONMENT" == "production" ]]; then
    for cmd in kubectl helm; do
      if command -v "$cmd" &>/dev/null; then
        success "$cmd: $(command -v $cmd)"
      else
        missing+=("$cmd")
      fi
    done
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing prerequisites: ${missing[*]}. Please install and retry."
  fi

  # Check Docker daemon
  if ! docker info &>/dev/null; then
    error "Docker daemon not running. Please start Docker and retry."
  fi

  success "All prerequisites satisfied"
}

# ─── Environment Configuration ───────────────────────────────────────
setup_environment() {
  header "Configuring Environment: $ENVIRONMENT"

  if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
      cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
      warn ".env created from .env.example — PLEASE UPDATE with real values before production use"
    else
      error "No .env or .env.example found. Cannot configure environment."
    fi
  fi

  source "$PROJECT_ROOT/.env" 2>/dev/null || true

  # Validate required variables
  local required_vars=("SECRET_KEY" "POSTGRES_PASSWORD" "REDIS_PASSWORD")
  if [[ "$ENVIRONMENT" == "production" || "$ENVIRONMENT" == "staging" ]]; then
    required_vars+=("ANTHROPIC_API_KEY")
  fi

  for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      warn "Missing required variable: $var"
    else
      success "$var: configured"
    fi
  done
}

# ─── Database Setup ──────────────────────────────────────────────────
setup_database() {
  header "Setting Up Database"

  log "Waiting for PostgreSQL to be ready..."
  local retries=30
  until docker exec nexus-postgres pg_isready -U "${POSTGRES_USER:-nexus}" &>/dev/null || [[ $retries -eq 0 ]]; do
    retries=$((retries - 1))
    sleep 2
  done

  if [[ $retries -eq 0 ]]; then
    error "PostgreSQL did not become ready in time"
  fi

  success "PostgreSQL is ready"

  log "Running database migrations..."
  cd "$PROJECT_ROOT/backend"
  if command -v alembic &>/dev/null; then
    alembic upgrade head 2>&1 | tee -a "$LOG_FILE"
    success "Database migrations applied"
  else
    warn "alembic not found — skipping migrations (run manually: cd backend && alembic upgrade head)"
  fi
}

# ─── Data Seeding ────────────────────────────────────────────────────
seed_data() {
  header "Seeding Platform Data"

  if [[ -f "$PROJECT_ROOT/scripts/seed_data.py" ]]; then
    log "Running data seeding pipeline..."
    cd "$PROJECT_ROOT"
    python3 scripts/seed_data.py \
      --suppliers 50 \
      --warehouses 12 \
      --shipments 300 \
      --disruptions 50 \
      --demand-days 365 \
      --output-dir data/seeds \
      2>&1 | tee -a "$LOG_FILE"
    success "Data seeding complete"
  else
    warn "seed_data.py not found — skipping data seeding"
  fi
}

# ─── Local Development Deploy ─────────────────────────────────────────
deploy_local() {
  header "Local Development Deployment"

  # Install Python dependencies
  log "Installing Python dependencies..."
  cd "$PROJECT_ROOT/backend"
  pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
  success "Python dependencies installed"

  # Install Node dependencies
  log "Installing Node.js dependencies..."
  cd "$PROJECT_ROOT/frontend"
  npm ci --silent 2>&1 | tee -a "$LOG_FILE"
  success "Node.js dependencies installed"

  # Start infrastructure
  log "Starting infrastructure services..."
  cd "$PROJECT_ROOT"
  docker compose up -d postgres redis zookeeper kafka mlflow 2>&1 | tee -a "$LOG_FILE"
  sleep 10
  setup_database
  seed_data

  success "Local development environment ready!"
  info "Backend API:    http://localhost:8000"
  info "API Docs:       http://localhost:8000/docs"
  info "Frontend:       http://localhost:3000"
  info "MLflow UI:      http://localhost:5000"
  info ""
  info "Start backend:  cd backend && uvicorn main:app --reload --port 8000"
  info "Start frontend: cd frontend && npm run dev"
}

# ─── Docker Deployment ────────────────────────────────────────────────
deploy_docker() {
  header "Docker Deployment"

  log "Building Docker images..."
  cd "$PROJECT_ROOT"
  docker compose build --parallel 2>&1 | tee -a "$LOG_FILE"
  success "Docker images built"

  log "Starting all services..."
  docker compose up -d 2>&1 | tee -a "$LOG_FILE"

  log "Waiting for services to be healthy..."
  sleep 30

  # Health checks
  local services=("nexus-postgres" "nexus-redis" "nexus-kafka" "nexus-api" "nexus-frontend")
  for service in "${services[@]}"; do
    if docker ps --filter "name=$service" --filter "status=running" --format "{{.Names}}" | grep -q "$service"; then
      success "$service: running"
    else
      warn "$service: not running — check logs with: docker logs $service"
    fi
  done

  setup_database
  seed_data

  # API health check
  log "Running API health check..."
  local api_retries=20
  until curl -sf http://localhost:8000/health &>/dev/null || [[ $api_retries -eq 0 ]]; do
    api_retries=$((api_retries - 1))
    sleep 3
  done

  if curl -sf http://localhost:8000/health &>/dev/null; then
    success "API health check passed"
  else
    warn "API health check failed — check: docker logs nexus-api"
  fi

  success "Docker deployment complete!"
  info ""
  info "Platform URL:   http://localhost:3000"
  info "API Docs:       http://localhost:8000/docs"
  info "Kafka UI:       http://localhost:8080"
  info "MLflow UI:      http://localhost:5000"
  info "Grafana:        http://localhost:3001"
  info "Prometheus:     http://localhost:9090"
  info ""
  info "View logs:      docker compose logs -f nexus-api"
  info "Stop:           docker compose down"
}

# ─── Kubernetes Deployment ────────────────────────────────────────────
deploy_kubernetes() {
  header "Kubernetes Deployment"
  local namespace="${K8S_NAMESPACE:-nexus}"
  local image_tag="${IMAGE_TAG:-latest}"

  log "Deploying to Kubernetes namespace: $namespace"
  log "Image tag: $image_tag"

  # Update image tags in manifests
  log "Configuring Kubernetes manifests..."
  cd "$PROJECT_ROOT"
  find k8s/ -name "*.yaml" -exec sed -i "s|IMAGE_TAG|$image_tag|g" {} \;

  # Apply manifests
  log "Applying Kubernetes manifests..."
  kubectl apply -f k8s/namespace.yaml 2>&1 | tee -a "$LOG_FILE"
  kubectl apply -f k8s/configmap.yaml -n "$namespace" 2>&1 | tee -a "$LOG_FILE"
  kubectl apply -f k8s/secrets.yaml -n "$namespace" 2>/dev/null || \
    warn "Secrets not found — ensure nexus-secrets Secret exists in namespace"
  kubectl apply -f k8s/ -n "$namespace" 2>&1 | tee -a "$LOG_FILE"

  # Wait for rollouts
  log "Waiting for deployment rollouts..."
  local deployments=("nexus-api" "nexus-worker" "nexus-frontend")
  for deployment in "${deployments[@]}"; do
    log "Waiting for $deployment..."
    kubectl rollout status deployment/"$deployment" -n "$namespace" --timeout=300s 2>&1 | tee -a "$LOG_FILE" || \
      warn "$deployment rollout timeout — check: kubectl describe deployment/$deployment -n $namespace"
  done

  # Verify pods
  log "Pod status:"
  kubectl get pods -n "$namespace" -o wide | tee -a "$LOG_FILE"

  success "Kubernetes deployment complete!"
  info "Access via: kubectl port-forward svc/nexus-frontend-svc 3000:3000 -n $namespace"
  info "API via:    kubectl port-forward svc/nexus-api-svc 8000:8000 -n $namespace"
}

# ─── Health Check ────────────────────────────────────────────────────
run_health_check() {
  header "Running Health Checks"

  local api_url="${API_URL:-http://localhost:8000}"

  log "Checking API health..."
  local response=$(curl -sf "$api_url/health" 2>/dev/null || echo '{"status":"unreachable"}')
  local api_status=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")

  if [[ "$api_status" == "healthy" ]]; then
    success "API Health: $api_status"
    echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  {k}: {v}') for k,v in d.get('checks',{}).items()]" 2>/dev/null || true
  else
    warn "API Health: $api_status"
  fi
}

# ─── Teardown ────────────────────────────────────────────────────────
teardown() {
  header "Tearing Down NEXUS Platform"
  warn "This will STOP and REMOVE all NEXUS containers. Data volumes will be preserved."
  read -r -p "Are you sure? [y/N] " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    cd "$PROJECT_ROOT"
    docker compose down --remove-orphans 2>&1 | tee -a "$LOG_FILE"
    success "All services stopped"
  else
    info "Teardown cancelled"
  fi
}

# ─── Main ────────────────────────────────────────────────────────────
main() {
  print_banner
  log "Deployment target: ${BOLD}$ENVIRONMENT${NC}"
  log "Timestamp: $TIMESTAMP"
  log "Log file: $LOG_FILE"

  check_prerequisites
  setup_environment

  case "$ENVIRONMENT" in
    local)       deploy_local ;;
    docker)      deploy_docker ;;
    k8s|kubernetes) deploy_kubernetes ;;
    staging)     ENVIRONMENT=staging deploy_docker ;;
    production)  ENVIRONMENT=production deploy_kubernetes ;;
    health)      run_health_check ;;
    teardown)    teardown ;;
    *)
      error "Unknown environment: $ENVIRONMENT
Valid options: local | docker | k8s | staging | production | health | teardown"
      ;;
  esac

  log "Deployment log saved to: $LOG_FILE"
  echo -e "\n${GREEN}${BOLD}🚀 NEXUS deployment complete!${NC}\n"
}

main "$@"
