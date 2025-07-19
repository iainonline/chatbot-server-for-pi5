#!/bin/bash
#
# Raspberry Pi 5 LED Control Script
# Controls the front LEDs on the Pi5
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${BLUE}[LED Control]${NC} $1"
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
        echo "Usage: sudo $0 [command]"
        exit 1
    fi
}

# Function to list available LEDs
list_leds() {
    log "Available LEDs on Raspberry Pi 5:"
    echo
    if [ -d "/sys/class/leds" ]; then
        for led in /sys/class/leds/*; do
            if [ -d "$led" ]; then
                led_name=$(basename "$led")
                brightness=$(cat "$led/brightness" 2>/dev/null || echo "unknown")
                max_brightness=$(cat "$led/max_brightness" 2>/dev/null || echo "unknown")
                trigger=$(cat "$led/trigger" 2>/dev/null | grep -o '\[.*\]' | tr -d '[]' || echo "none")
                
                echo -e "  ${CYAN}$led_name${NC}"
                echo -e "    Brightness: $brightness/$max_brightness"
                echo -e "    Trigger: $trigger"
                echo
            fi
        done
    else
        echo -e "${RED}Error: LED control not available${NC}"
    fi
}

# Function to control LED
control_led() {
    local led_name=$1
    local action=$2
    local led_path="/sys/class/leds/$led_name"
    
    if [ ! -d "$led_path" ]; then
        echo -e "${RED}Error: LED '$led_name' not found${NC}"
        return 1
    fi
    
    case $action in
        "on")
            echo "255" > "$led_path/brightness"
            echo "none" > "$led_path/trigger"
            log "${GREEN}✓${NC} LED '$led_name' turned ON"
            ;;
        "off")
            echo "0" > "$led_path/brightness"
            echo "none" > "$led_path/trigger"
            log "${GREEN}✓${NC} LED '$led_name' turned OFF"
            ;;
        "blink")
            echo "timer" > "$led_path/trigger"
            log "${GREEN}✓${NC} LED '$led_name' set to BLINK"
            ;;
        "heartbeat")
            echo "heartbeat" > "$led_path/trigger"
            log "${GREEN}✓${NC} LED '$led_name' set to HEARTBEAT"
            ;;
        "activity")
            echo "mmc0" > "$led_path/trigger" 2>/dev/null || echo "disk-activity" > "$led_path/trigger" 2>/dev/null
            log "${GREEN}✓${NC} LED '$led_name' set to ACTIVITY"
            ;;
        "default")
            echo "default-on" > "$led_path/trigger"
            log "${GREEN}✓${NC} LED '$led_name' restored to DEFAULT"
            ;;
        *)
            echo -e "${RED}Error: Unknown action '$action'${NC}"
            echo "Available actions: on, off, blink, heartbeat, activity, default"
            return 1
            ;;
    esac
}

# Function to create PiBot status patterns
pibot_status() {
    local status=$1
    
    case $status in
        "initializing")
            log "Setting PiBot INITIALIZING pattern..."
            # Fast blinking yellow (using PWR LED for yellow effect)
            echo "timer" > "/sys/class/leds/PWR/trigger"
            echo "100" > "/sys/class/leds/PWR/delay_on" 2>/dev/null || true
            echo "100" > "/sys/class/leds/PWR/delay_off" 2>/dev/null || true
            control_led "ACT" "off"
            ;;
        "no_network")
            log "Setting PiBot NO NETWORK pattern..."
            # Solid red (PWR LED)
            control_led "PWR" "on"
            control_led "ACT" "off"
            ;;
        "server_down")
            log "Setting PiBot SERVER DOWN pattern..."
            # Solid yellow (PWR LED dimmed or using different pattern)
            echo "timer" > "/sys/class/leds/PWR/trigger"
            echo "500" > "/sys/class/leds/PWR/delay_on" 2>/dev/null || true
            echo "500" > "/sys/class/leds/PWR/delay_off" 2>/dev/null || true
            control_led "ACT" "off"
            ;;
        "both_issues")
            log "Setting PiBot BOTH ISSUES pattern..."
            # Blinking red and yellow alternating
            echo "timer" > "/sys/class/leds/PWR/trigger"
            echo "250" > "/sys/class/leds/PWR/delay_on" 2>/dev/null || true
            echo "250" > "/sys/class/leds/PWR/delay_off" 2>/dev/null || true
            echo "timer" > "/sys/class/leds/ACT/trigger"
            echo "250" > "/sys/class/leds/ACT/delay_on" 2>/dev/null || true
            echo "250" > "/sys/class/leds/ACT/delay_off" 2>/dev/null || true
            ;;
        "running")
            log "Setting PiBot RUNNING pattern..."
            # Solid green (ACT LED), PWR LED off
            control_led "PWR" "off"
            control_led "ACT" "on"
            ;;
        "running_heartbeat")
            log "Setting PiBot RUNNING HEARTBEAT pattern..."
            # Brief off pulse for green LED (9.5s on, 0.5s off)
            control_led "PWR" "off"
            control_led "ACT" "off"
            sleep 0.5
            control_led "ACT" "on"
            ;;
        "starting")
            log "Setting PiBot STARTING pattern..."
            # Power LED blinks slowly, Activity LED off
            control_led "PWR" "blink"
            control_led "ACT" "off"
            ;;
        "error")
            log "Setting PiBot ERROR pattern..."
            # Both LEDs blink rapidly
            control_led "PWR" "heartbeat"
            control_led "ACT" "heartbeat"
            ;;
        "shutdown")
            log "Setting PiBot SHUTDOWN pattern..."
            # Both LEDs off
            control_led "PWR" "off"
            control_led "ACT" "off"
            ;;
        "demo")
            log "Running LED demo sequence..."
            echo "Power LED ON..."
            control_led "PWR" "on"
            sleep 2
            echo "Activity LED ON..."
            control_led "ACT" "on"
            sleep 2
            echo "Both LEDs BLINK..."
            control_led "PWR" "blink"
            control_led "ACT" "blink"
            sleep 5
            echo "Heartbeat pattern..."
            control_led "PWR" "heartbeat"
            control_led "ACT" "heartbeat"
            sleep 5
            echo "Restoring defaults..."
            control_led "PWR" "default"
            control_led "ACT" "activity"
            ;;
        *)
            echo -e "${RED}Error: Unknown status '$status'${NC}"
            echo "Available statuses: initializing, no_network, server_down, both_issues, running, running_heartbeat, starting, error, shutdown, demo"
            return 1
            ;;
    esac
}

# Function to show usage
show_usage() {
    echo -e "${CYAN}Raspberry Pi 5 LED Control Script${NC}"
    echo
    echo "Usage: sudo $0 [command] [options]"
    echo
    echo "Commands:"
    echo "  list                     - List all available LEDs"
    echo "  control [led] [action]   - Control specific LED"
    echo "  pibot [status]          - Set PiBot status pattern"
    echo "  demo                    - Run LED demo sequence"
    echo
    echo "LED Names (common on Pi5):"
    echo "  PWR                     - Power LED (red)"
    echo "  ACT                     - Activity LED (green)"
    echo
    echo "Actions:"
    echo "  on, off, blink, heartbeat, activity, default"
    echo
    echo "PiBot Status Patterns:"
    echo "  initializing            - Fast blinking yellow (startup)"
    echo "  no_network              - Solid red (no internet)"
    echo "  server_down             - Slow blinking yellow (server not running)"
    echo "  both_issues             - Alternating red/yellow blink (both problems)"
    echo "  running                 - Solid green (all good)"
    echo "  running_heartbeat       - Green with 0.5s off pulse (heartbeat)"
    echo "  starting, error, shutdown, demo"
    echo
    echo "Examples:"
    echo "  sudo $0 list"
    echo "  sudo $0 control PWR on"
    echo "  sudo $0 control ACT blink"
    echo "  sudo $0 pibot running"
    echo "  sudo $0 demo"
}

# Main execution
main() {
    check_root
    
    case "${1:-help}" in
        "list")
            list_leds
            ;;
        "control")
            if [ $# -ne 3 ]; then
                echo -e "${RED}Error: Missing arguments${NC}"
                echo "Usage: sudo $0 control [led_name] [action]"
                exit 1
            fi
            control_led "$2" "$3"
            ;;
        "pibot")
            if [ $# -ne 2 ]; then
                echo -e "${RED}Error: Missing status argument${NC}"
                echo "Usage: sudo $0 pibot [status]"
                exit 1
            fi
            pibot_status "$2"
            ;;
        "demo")
            pibot_status "demo"
            ;;
        "help"|"-h"|"--help"|*)
            show_usage
            ;;
    esac
}

# Run main function
main "$@"
