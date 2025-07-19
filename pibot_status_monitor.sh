#!/bin/bash
#
# PiBot Status Monitor with LED Indicators
# Continuously monitors network and server status, updates LEDs accordingly
#

# Configuration
SERVICE_NAME="ollama-chatbot"
LED_CONTROL="/home/iain/Pi5-LLM/led_control.sh"
CHECK_INTERVAL=5  # Check every 5 seconds
HEARTBEAT_INTERVAL=10  # Heartbeat every 10 seconds
HEARTBEAT_DURATION=0.5   # Heartbeat off duration (0.5 seconds)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Status tracking
current_status=""
heartbeat_counter=0
initialization_done=false

# Function to log messages with timestamp
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

# Function to show LED status table
show_led_table() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                    🤖 PiBot LED Status Indicators                 ║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC} LED Pattern                     ${CYAN}║${NC} Status Description              ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC} ${YELLOW}⚡ Fast Blinking Yellow${NC}          ${CYAN}║${NC} 🔄 Initializing System         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC} ${RED}🔴 Solid Red${NC}                     ${CYAN}║${NC} 🌐 No Network Connection       ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC} ${YELLOW}🟡 Slow Blinking Yellow${NC}          ${CYAN}║${NC} 🚫 Server Not Running          ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC} ${RED}🔴${YELLOW}🟡${NC} Alternating Red/Yellow      ${CYAN}║${NC} ❌ Network + Server Issues     ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC} ${GREEN}🟢 Solid Green${NC}                   ${CYAN}║${NC} ✅ All Systems Running         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC} ${GREEN}🟢💓${NC} Green with Heartbeat         ${CYAN}║${NC} ❤️  Healthy Operation (9.5s on)${CYAN}║${NC}"
    echo -e "${CYAN}║${NC} 🔵 All LEDs Off                 ${CYAN}║${NC} 🛑 System Shutdown             ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo
}

# Function to set LED status with error handling
set_led_status() {
    local status=$1
    if [ -x "$LED_CONTROL" ]; then
        sudo "$LED_CONTROL" pibot "$status" >/dev/null 2>&1 || true
    fi
}

# Function to check network connectivity
check_network() {
    # Test multiple servers to ensure connectivity
    ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 || \
    ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1 || \
    ping -c 1 -W 2 208.67.222.222 >/dev/null 2>&1
}

# Function to check server status
check_server() {
    systemctl is-active --quiet "$SERVICE_NAME" && \
    curl -s --connect-timeout 3 --max-time 5 "http://localhost:8080" >/dev/null 2>&1
}

# Function to determine and set status
update_status() {
    local network_ok=false
    local server_ok=false
    local new_status=""
    
    # Check network
    if check_network; then
        network_ok=true
    fi
    
    # Check server
    if check_server; then
        server_ok=true
    fi
    
    # Determine status
    if [ "$network_ok" = true ] && [ "$server_ok" = true ]; then
        new_status="running"
    elif [ "$network_ok" = false ] && [ "$server_ok" = false ]; then
        new_status="both_issues"
    elif [ "$network_ok" = false ]; then
        new_status="no_network"
    elif [ "$server_ok" = false ]; then
        new_status="server_down"
    fi
    
    # Update LEDs if status changed
    if [ "$new_status" != "$current_status" ]; then
        current_status="$new_status"
        case $new_status in
            "running")
                log "${GREEN}✅ All systems operational${NC}"
                set_led_status "running"
                ;;
            "no_network")
                log "${RED}🌐 Network connectivity lost${NC}"
                set_led_status "no_network"
                ;;
            "server_down")
                log "${YELLOW}🚫 Server not responding${NC}"
                set_led_status "server_down"
                ;;
            "both_issues")
                log "${RED}❌ Network and server issues detected${NC}"
                set_led_status "both_issues"
                ;;
        esac
        heartbeat_counter=0  # Reset heartbeat counter on status change
    fi
}

# Function to handle heartbeat for running status
handle_heartbeat() {
    if [ "$current_status" = "running" ]; then
        heartbeat_counter=$((heartbeat_counter + CHECK_INTERVAL))
        
        if [ $heartbeat_counter -ge $HEARTBEAT_INTERVAL ]; then
            log "${GREEN}💓 System heartbeat${NC}"
            set_led_status "running_heartbeat"
            heartbeat_counter=0
        fi
    fi
}

# Function to handle initialization
initialize() {
    if [ "$initialization_done" = false ]; then
        show_led_table
        log "${YELLOW}🔄 Initializing PiBot status monitor...${NC}"
        set_led_status "initializing"
        sleep 3  # Show initialization for 3 seconds
        initialization_done=true
        log "${BLUE}✓ Initialization complete${NC}"
    fi
}

# Function to cleanup on exit
cleanup() {
    log "${BLUE}🛑 Shutting down status monitor${NC}"
    set_led_status "shutdown"
    exit 0
}

# Trap signals for cleanup
trap cleanup SIGINT SIGTERM

# Function to show usage
show_usage() {
    echo -e "${CYAN}PiBot Status Monitor with LED Indicators${NC}"
    echo
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  --daemon, -d        Run as background daemon"
    echo "  --interval N        Check interval in seconds (default: 5)"
    echo "  --heartbeat N       Heartbeat interval in seconds (default: 10)"
    echo "  --table-only        Show LED table and exit"
    echo "  --help, -h          Show this help"
    echo
    echo "LED Status Indicators:"
    show_led_table
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --daemon|-d)
            DAEMON_MODE=true
            shift
            ;;
        --interval)
            CHECK_INTERVAL="$2"
            shift 2
            ;;
        --heartbeat)
            HEARTBEAT_INTERVAL="$2"
            shift 2
            ;;
        --table-only)
            show_led_table
            exit 0
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    if [ "$DAEMON_MODE" = true ]; then
        log "${BLUE}🔧 Starting PiBot status monitor in daemon mode${NC}"
        exec > /dev/null 2>&1
    else
        log "${BLUE}🤖 Starting PiBot status monitor${NC}"
        log "Check interval: ${CHECK_INTERVAL}s, Heartbeat interval: ${HEARTBEAT_INTERVAL}s"
        log "Press Ctrl+C to stop"
        echo
    fi
    
    # Initialize
    initialize
    
    # Main monitoring loop
    while true; do
        update_status
        handle_heartbeat
        sleep "$CHECK_INTERVAL"
    done
}

# Check if LED control script exists
if [ ! -x "$LED_CONTROL" ]; then
    echo -e "${RED}Error: LED control script not found or not executable: $LED_CONTROL${NC}"
    exit 1
fi

# Start main function
main "$@"
