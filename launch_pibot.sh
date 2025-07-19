#!/bin/bash
#
# PiBot Launch Script
# Launches the PiBot web interface in the default browser
# Waits for the service to be ready before opening browser
#

# Configuration
SERVICE_NAME="ollama-chatbot"
MAX_WAIT_TIME=60  # Maximum time to wait for service (seconds)
CHECK_INTERVAL=2  # Check interval (seconds)
LED_CONTROL="/home/iain/Pi5-LLM/led_control.sh"
STATUS_MONITOR="/home/iain/Pi5-LLM/pibot_status_monitor.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log messages with timestamp
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

# Function to set LED status
set_led_status() {
    local status=$1
    if [ -x "$LED_CONTROL" ]; then
        sudo "$LED_CONTROL" pibot "$status" 2>/dev/null || true
    fi
}

# Function to start status monitor daemon
start_status_monitor() {
    # Check if status monitor is already running
    if ! pgrep -f "pibot_status_monitor.sh" > /dev/null; then
        if [ -x "$STATUS_MONITOR" ]; then
            log "Starting LED status monitor daemon..."
            nohup "$STATUS_MONITOR" --daemon > /dev/null 2>&1 &
            sleep 2  # Give it time to start
        fi
    fi
}

# Function to get local IP address
get_local_ip() {
    # Use the same method as the app
    python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    print(ip)
except:
    print('localhost')
"
}

# Function to check if service is running
check_service_status() {
    systemctl is-active --quiet "$SERVICE_NAME"
    return $?
}

# Function to check if web server is responding
check_web_server() {
    local ip=$(get_local_ip)
    local url="http://${ip}:8080"
    
    # Try to connect to the web server
    curl -s --connect-timeout 3 --max-time 5 "$url" > /dev/null 2>&1
    return $?
}

# Function to wait for service to be ready
wait_for_service() {
    local waited=0
    
    log "Checking PiBot service status..."
    
    while [ $waited -lt $MAX_WAIT_TIME ]; do
        if check_service_status; then
            log "${GREEN}✓${NC} PiBot service is running"
            
            # Now check if web server is responding
            log "Waiting for web server to respond..."
            local web_waited=0
            while [ $web_waited -lt 30 ]; do
                if check_web_server; then
                    log "${GREEN}✓${NC} Web server is responding"
                    return 0
                fi
                sleep $CHECK_INTERVAL
                web_waited=$((web_waited + CHECK_INTERVAL))
            done
            
            log "${YELLOW}⚠${NC} Service running but web server not responding"
            return 1
        else
            log "${YELLOW}...${NC} Waiting for PiBot service (${waited}s/${MAX_WAIT_TIME}s)"
            sleep $CHECK_INTERVAL
            waited=$((waited + CHECK_INTERVAL))
        fi
    done
    
    log "${RED}✗${NC} PiBot service failed to start within ${MAX_WAIT_TIME} seconds"
    return 1
}

# Function to launch browser
launch_browser() {
    local ip=$(get_local_ip)
    local url="http://${ip}:8080"
    
    log "Opening PiBot interface: $url"
    
    # Try different browsers in order of preference
    if command -v chromium-browser > /dev/null; then
        chromium-browser --start-fullscreen "$url" > /dev/null 2>&1 &
        log "${GREEN}✓${NC} Launched in Chromium"
    elif command -v firefox > /dev/null; then
        firefox "$url" > /dev/null 2>&1 &
        log "${GREEN}✓${NC} Launched in Firefox"
    elif command -v x-www-browser > /dev/null; then
        x-www-browser "$url" > /dev/null 2>&1 &
        log "${GREEN}✓${NC} Launched in default browser"
    else
        log "${RED}✗${NC} No suitable browser found"
        # Show notification with the URL
        notify-send "PiBot Ready" "Open browser to: $url" --icon=applications-internet
        return 1
    fi
    
    return 0
}

# Main execution
main() {
    log "${BLUE}🤖 PiBot Auto-Launch Script${NC}"
    log "=================================================="
    
    # Show LED status table
    if [ -x "$STATUS_MONITOR" ]; then
        "$STATUS_MONITOR" --table-only
    fi
    
    # Set starting LED pattern
    set_led_status "initializing"
    
    # Wait a bit for desktop to load
    sleep 5
    
    # Start the status monitor daemon
    start_status_monitor
    
    # Wait for service to be ready
    if wait_for_service; then
        # Service is ready, launch browser
        if launch_browser; then
            log "${GREEN}✓${NC} PiBot interface launched successfully!"
            # Status monitor will handle LED updates from here
        else
            log "${YELLOW}⚠${NC} Browser launch failed, but service is running"
            # Status monitor will handle LED updates from here
        fi
    else
        log "${RED}✗${NC} PiBot service is not available"
        # Status monitor will show error status
        
        # Show error notification
        notify-send "PiBot Startup Error" "PiBot service failed to start. Check system logs." --icon=dialog-error
        
        # Try to start the service manually (requires sudo permissions)
        log "Attempting to start service manually..."
        if systemctl --user is-enabled "$SERVICE_NAME" > /dev/null 2>&1; then
            systemctl --user start "$SERVICE_NAME"
        else
            # Show instructions for manual start
            zenity --info --title="PiBot Service" --text="PiBot service is not running.\n\nTo start manually, run:\nsudo systemctl start $SERVICE_NAME" 2>/dev/null || true
        fi
    fi
    
    log "=================================================="
    log "${BLUE}💡 LED Status Monitor is running in background${NC}"
    log "${BLUE}   Use 'pkill -f pibot_status_monitor' to stop${NC}"
}

# Run main function
main "$@"
