#!/usr/bin/env bash
# =============================================================================
# run_tests.sh - Script de Testing Unificado para GuepardAI
# =============================================================================
# Ejecuta todos los tests del proyecto (Backend Python + Frontend Angular)
# con una sola instrucción:
#
#   bash run_tests.sh           → Corre todo
#   bash run_tests.sh backend   → Solo tests del backend
#   bash run_tests.sh frontend  → Solo tests del frontend
#   bash run_tests.sh ci        → Modo CI: falla rápido, sin colores, con coverage
#
# PREREQUISITOS:
#   - Docker corriendo (para la BD de test)
#   - Python con dependencias instaladas (pip install -r backend/requirements.txt)
#   - Node.js con Angular CLI (npm install en frontend/)
# =============================================================================

set -e  # Detener si cualquier comando falla

# ─────────────────────────────────────────────────────────────────────────────
# Colores para output legible
# ─────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ─────────────────────────────────────────────────────────────────────────────
# Variables de control
# ─────────────────────────────────────────────────────────────────────────────
MODE=${1:-"all"}           # all | backend | frontend | ci
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
TEST_DB_CONTAINER="guepard_ai_db_test"
BACKEND_PASSED=false
FRONTEND_PASSED=false

# ─────────────────────────────────────────────────────────────────────────────
print_header() {
    echo ""
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  GuepardAI Test Suite - $1 ${NC}"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}▶ $1${NC}"
}

print_ok() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_fail() {
    echo -e "${RED}❌ $1${NC}"
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN: Levantar base de datos de test
# ─────────────────────────────────────────────────────────────────────────────
start_test_db() {
    print_step "Verificando BD de test PostgreSQL (puerto 5433)..."

    if docker ps --format '{{.Names}}' | grep -q "^${TEST_DB_CONTAINER}$"; then
        print_ok "Contenedor '$TEST_DB_CONTAINER' ya está corriendo."
    else
        print_step "Levantando contenedor de test..."
        docker compose -f "$SCRIPT_DIR/docker-compose.test.yml" up -d

        print_step "Esperando que PostgreSQL esté listo..."
        for i in {1..20}; do
            if docker exec "$TEST_DB_CONTAINER" pg_isready -U root -d ai_db_test -q 2>/dev/null; then
                print_ok "BD de test lista."
                break
            fi
            if [ $i -eq 20 ]; then
                print_fail "BD de test no respondió a tiempo. Abortando."
                exit 1
            fi
            sleep 2
        done
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN: Preparar .env.test si no existe
# ─────────────────────────────────────────────────────────────────────────────
setup_env_test() {
    if [ ! -f "$BACKEND_DIR/.env.test" ]; then
        print_warn ".env.test no encontrado. Creando desde .env.test.example..."
        cp "$BACKEND_DIR/.env.test.example" "$BACKEND_DIR/.env.test"
        print_ok ".env.test creado."
    else
        print_ok ".env.test existe."
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN: Ejecutar tests del Backend
# ─────────────────────────────────────────────────────────────────────────────
run_backend_tests() {
    print_header "Backend (Python / pytest)"

    start_test_db
    setup_env_test

    print_step "Ejecutando pytest con cobertura de código..."
    echo ""

    PYTEST_ARGS="--cov=agents --cov-report=term-missing --cov-report=html:htmlcov -v"

    if [ "$MODE" = "ci" ]; then
        # En CI: falla rápido, sin colores, con reporte XML para GitHub Actions
        PYTEST_ARGS="$PYTEST_ARGS --tb=short --no-header -p no:cacheprovider --cov-report=xml:coverage.xml"
    fi

    cd "$BACKEND_DIR"
    if python -m pytest $PYTEST_ARGS tests/; then
        BACKEND_PASSED=true
        echo ""
        print_ok "Backend: TODOS LOS TESTS PASARON"
        if [ "$MODE" != "ci" ]; then
            echo -e "  ${CYAN}Reporte de cobertura: ${BACKEND_DIR}/htmlcov/index.html${NC}"
        fi
    else
        print_fail "Backend: TESTS FALLARON"
        return 1
    fi
    cd "$SCRIPT_DIR"
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN: Ejecutar tests del Frontend
# ─────────────────────────────────────────────────────────────────────────────
run_frontend_tests() {
    print_header "Frontend (Angular / Karma + Jasmine)"

    print_step "Verificando dependencias de Node.js..."
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        print_step "node_modules no encontrado. Instalando dependencias..."
        cd "$FRONTEND_DIR" && npm install --silent
        cd "$SCRIPT_DIR"
    else
        print_ok "node_modules existe."
    fi

    print_step "Ejecutando ng test..."
    echo ""

    cd "$FRONTEND_DIR"
    if [ "$MODE" = "ci" ]; then
        # En CI: sin ventana del navegador, sin modo watch
        if npx ng test --watch=false --browsers=ChromeHeadless --no-progress; then
            FRONTEND_PASSED=true
            echo ""
            print_ok "Frontend: TODOS LOS TESTS PASARON"
        else
            print_fail "Frontend: TESTS FALLARON"
            cd "$SCRIPT_DIR"
            return 1
        fi
    else
        if npx ng test --watch=false --browsers=Chrome; then
            FRONTEND_PASSED=true
            echo ""
            print_ok "Frontend: TODOS LOS TESTS PASARON"
        else
            print_fail "Frontend: TESTS FALLARON"
            cd "$SCRIPT_DIR"
            return 1
        fi
    fi
    cd "$SCRIPT_DIR"
}

# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  RESUMEN FINAL${NC}"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════${NC}"

    if [ "$MODE" = "all" ] || [ "$MODE" = "ci" ]; then
        if $BACKEND_PASSED; then
            echo -e "  Backend  : ${GREEN}${BOLD}PASSED ✅${NC}"
        else
            echo -e "  Backend  : ${RED}${BOLD}FAILED ❌${NC}"
        fi
        if $FRONTEND_PASSED; then
            echo -e "  Frontend : ${GREEN}${BOLD}PASSED ✅${NC}"
        else
            echo -e "  Frontend : ${RED}${BOLD}FAILED ❌${NC}"
        fi
    elif [ "$MODE" = "backend" ]; then
        if $BACKEND_PASSED; then
            echo -e "  Backend  : ${GREEN}${BOLD}PASSED ✅${NC}"
        else
            echo -e "  Backend  : ${RED}${BOLD}FAILED ❌${NC}"
        fi
    elif [ "$MODE" = "frontend" ]; then
        if $FRONTEND_PASSED; then
            echo -e "  Frontend : ${GREEN}${BOLD}PASSED ✅${NC}"
        else
            echo -e "  Frontend : ${RED}${BOLD}FAILED ❌${NC}"
        fi
    fi

    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════${NC}"
    echo ""

    # Código de salida: 0 = éxito, 1 = fallo (importante para CI)
    if $BACKEND_PASSED && $FRONTEND_PASSED; then
        exit 0
    elif [ "$MODE" = "backend" ] && $BACKEND_PASSED; then
        exit 0
    elif [ "$MODE" = "frontend" ] && $FRONTEND_PASSED; then
        exit 0
    else
        exit 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
case "$MODE" in
    "backend")
        run_backend_tests
        FRONTEND_PASSED=true  # No aplica
        ;;
    "frontend")
        run_frontend_tests
        BACKEND_PASSED=true   # No aplica
        ;;
    "all"|"ci")
        run_backend_tests
        run_frontend_tests
        ;;
    *)
        echo -e "${RED}Modo desconocido: '$MODE'${NC}"
        echo "Uso: bash run_tests.sh [all|backend|frontend|ci]"
        exit 1
        ;;
esac

print_summary
