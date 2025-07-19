#!/bin/bash
#
# PiBot Complete Setup Verification & Summary
# Final verification of all PiBot components and auto-startup configuration
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Header
echo -e "${PURPLE}======================================================================${NC}"
echo -e "${PURPLE}                    🤖 PiBot Final Setup Summary                      ${NC}"
echo -e "${PURPLE}              Raspberry Pi 5 Ollama Chatbot Auto-Startup            ${NC}"
echo -e "${PURPLE}======================================================================${NC}"
echo

# Function to check status with icon
check_status() {
    local description=$1
    local command=$2
    local success_msg=$3
    local error_msg=$4
    
    echo -n "  $description..."
    if eval "$command" >/dev/null 2>&1; then
        echo -e " ${GREEN}✅ $success_msg${NC}"
        return 0
    else
        echo -e " ${RED}❌ $error_msg${NC}"
        return 1
    fi
}

# Get system info
get_local_ip() {
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

LOCAL_IP=$(get_local_ip)
PIBOT_URL="http://${LOCAL_IP}:8080"

echo -e "${CYAN}📋 System Information${NC}"
echo "  🖥️  Device: Raspberry Pi 5"
echo "  🌐 Local IP: $LOCAL_IP"
echo "  🔗 PiBot URL: $PIBOT_URL"
echo "  📅 Date: $(date)"
echo

echo -e "${CYAN}🔍 Service Status Verification${NC}"
check_status "SystemD Service Installed" "[ -f /etc/systemd/system/ollama-chatbot.service ]" "Service file exists" "Service file missing"
check_status "Service Enabled for Boot" "systemctl is-enabled ollama-chatbot" "Auto-start enabled" "Not enabled"
check_status "Service Currently Running" "systemctl is-active ollama-chatbot" "Service active" "Service not running"
check_status "LED Monitor Service" "systemctl is-active pibot-status-monitor" "LED monitor active" "LED monitor not running"
check_status "Web Server Responding" "curl -s --connect-timeout 3 $PIBOT_URL" "Web server OK" "Web server not responding"

echo
echo -e "${CYAN}📁 File Structure Verification${NC}"
check_status "Main Application" "[ -f /home/iain/Pi5-LLM/app.py ]" "Found" "Missing"
check_status "Launch Script" "[ -x /home/iain/Pi5-LLM/launch_pibot.sh ]" "Executable" "Missing or not executable"
check_status "LED Control Script" "[ -x /home/iain/Pi5-LLM/led_control.sh ]" "Executable" "Missing or not executable"
check_status "Status Monitor Script" "[ -x /home/iain/Pi5-LLM/pibot_status_monitor.sh ]" "Executable" "Missing or not executable"
check_status "Autostart Desktop Entry" "[ -f ~/.config/autostart/pibot-browser.desktop ]" "Found" "Missing"
check_status "Database File" "[ -f /home/iain/Pi5-LLM/instance/chatbot.db ]" "Found" "Missing"
check_status "Gunicorn Config" "[ -f /home/iain/Pi5-LLM/gunicorn.conf.py ]" "Found" "Missing"

echo
echo -e "${CYAN}🔧 Dependencies Verification${NC}"
check_status "Python Virtual Environment" "[ -d /home/iain/Pi5-LLM/.venv ]" "Found" "Missing"
check_status "Gunicorn Installed" "[ -x /home/iain/Pi5-LLM/.venv/bin/gunicorn ]" "Installed" "Missing"
check_status "Browser Available" "command -v chromium-browser || command -v firefox" "Found" "No browser found"
check_status "Ollama Service" "command -v ollama" "Installed" "Not installed"

echo
echo -e "${CYAN}💾 Database Status${NC}"
if [ -f "/home/iain/Pi5-LLM/instance/chatbot.db" ]; then
    DB_SIZE=$(du -h "/home/iain/Pi5-LLM/instance/chatbot.db" | cut -f1)
    echo "  📊 Database size: $DB_SIZE"
    echo "  🔑 Default admin login: admin / admin123"
    echo "  ⚠️  Remember to change the admin password!"
else
    echo -e "  ${RED}❌ Database not found${NC}"
fi

echo
echo -e "${CYAN}🚀 Auto-Startup Sequence${NC}"
echo "  1️⃣  Pi5 boots → systemd starts ollama-chatbot.service"
echo "  2️⃣  LED status monitor starts → shows initialization pattern"
echo "  3️⃣  Desktop environment loads"
echo "  4️⃣  Autostart launches launch_pibot.sh → shows LED table"
echo "  5️⃣  Browser opens to PiBot login page"
echo "  6️⃣  LED monitor continuously shows system status"

echo
echo -e "${CYAN}💡 LED Status System${NC}"
if [ -x "/home/iain/Pi5-LLM/pibot_status_monitor.sh" ]; then
    /home/iain/Pi5-LLM/pibot_status_monitor.sh --table-only
fi

echo
echo -e "${CYAN}🎮 LED Manual Controls${NC}"
echo "  Status monitor:    sudo systemctl start/stop pibot-status-monitor"
echo "  Manual LED control: sudo /home/iain/Pi5-LLM/led_control.sh [command]"
echo "  Show LED table:     /home/iain/Pi5-LLM/pibot_status_monitor.sh --table-only"

echo
echo -e "${CYAN}🎮 Manual Controls${NC}"
echo "  Start service: sudo systemctl start ollama-chatbot"
echo "  Stop service:  sudo systemctl stop ollama-chatbot"
echo "  LED monitor:   sudo systemctl start/stop pibot-status-monitor"
echo "  View logs:     sudo journalctl -u ollama-chatbot -f"
echo "  Test launch:   /home/iain/Pi5-LLM/launch_pibot.sh"

echo
echo -e "${CYAN}🌐 Network Access${NC}"
echo "  Local:    $PIBOT_URL"
echo "  Network:  http://${LOCAL_IP}:8080 (from other devices)"
echo "  External: Requires port forwarding on port 8080"

echo
# Final test
echo -e "${CYAN}🧪 Final Integration Test${NC}"
if systemctl is-active --quiet ollama-chatbot && curl -s --connect-timeout 3 "$PIBOT_URL" >/dev/null; then
    echo -e "  ${GREEN}🎉 SUCCESS! PiBot is ready for auto-startup!${NC}"
    echo -e "  ${GREEN}✅ Service running, web server responding${NC}"
    echo -e "  ${GREEN}✅ Ready to test with: sudo reboot${NC}"
    
    # Set LED to running status
    if [ -x "/home/iain/Pi5-LLM/led_control.sh" ]; then
        sudo /home/iain/Pi5-LLM/led_control.sh pibot running 2>/dev/null || true
    fi
else
    echo -e "  ${RED}❌ Issues detected - check service status${NC}"
    echo -e "  ${YELLOW}💡 Try: sudo systemctl restart ollama-chatbot${NC}"
    
    # Set LED to error status
    if [ -x "/home/iain/Pi5-LLM/led_control.sh" ]; then
        sudo /home/iain/Pi5-LLM/led_control.sh pibot error 2>/dev/null || true
    fi
fi

echo
echo -e "${PURPLE}======================================================================${NC}"
echo -e "${PURPLE}                           🎯 Next Steps                             ${NC}"
echo -e "${PURPLE}======================================================================${NC}"
echo -e "${YELLOW}1. Reboot to test auto-startup: ${CYAN}sudo reboot${NC}"
echo -e "${YELLOW}2. Change admin password after first login${NC}"
echo -e "${YELLOW}3. Install Ollama models: ${CYAN}ollama pull llama2${NC}"
echo -e "${YELLOW}4. Enjoy your local AI chatbot! 🤖${NC}"
echo
