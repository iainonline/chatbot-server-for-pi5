#!/bin/bash
# PiBot Auto-Start Setup Script
# This script sets up the chatbot to start automatically at boot

set -e

echo "🤖 PiBot Auto-Start Setup"
echo "========================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}❌ This script should NOT be run as root${NC}"
   echo "Please run as regular user: ./setup_autostart.sh"
   exit 1
fi

# Get current user and working directory
USER=$(whoami)
WORK_DIR=$(pwd)

echo -e "${BLUE}👤 User: ${USER}${NC}"
echo -e "${BLUE}📁 Directory: ${WORK_DIR}${NC}"

# Stop any running development server
echo -e "${YELLOW}🛑 Stopping development server...${NC}"
pkill -f "python.*app.py" || true

# Install the systemd service
echo -e "${YELLOW}📋 Installing systemd service...${NC}"
sudo cp ollama-chatbot.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable the service to start at boot
echo -e "${YELLOW}🔧 Enabling auto-start at boot...${NC}"
sudo systemctl enable ollama-chatbot.service

# Start the service now
echo -e "${YELLOW}🚀 Starting PiBot service...${NC}"
sudo systemctl start ollama-chatbot.service

# Wait a moment for service to start
sleep 3

# Check service status
echo -e "${YELLOW}📊 Checking service status...${NC}"
if sudo systemctl is-active --quiet ollama-chatbot.service; then
    echo -e "${GREEN}✅ PiBot service is running!${NC}"
    
    # Get local IP
    LOCAL_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    print(ip)
except:
    print('localhost')
")
    
    echo -e "${GREEN}🌐 Server URLs:${NC}"
    echo -e "   Local:   http://localhost:8080"
    echo -e "   Network: http://${LOCAL_IP}:8080"
    
else
    echo -e "${RED}❌ Failed to start PiBot service${NC}"
    echo "Checking logs..."
    sudo journalctl -u ollama-chatbot.service --no-pager -n 20
    exit 1
fi

# Create desktop auto-launch script
echo -e "${YELLOW}🖥️  Setting up desktop auto-launch...${NC}"

# Create autostart directory if it doesn't exist
mkdir -p ~/.config/autostart

# Create desktop entry for auto-launch
cat > ~/.config/autostart/pibot-browser.desktop << EOF
[Desktop Entry]
Type=Application
Name=PiBot Browser
Comment=Launch PiBot web interface at startup
Exec=/home/${USER}/Pi5-LLM/launch_pibot.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

# Create the browser launch script
cat > launch_pibot.sh << 'EOF'
#!/bin/bash
# Wait for network and service to be ready
sleep 10

# Get local IP
LOCAL_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    print(ip)
except:
    print('localhost')
")

# Wait for service to be fully ready
for i in {1..30}; do
    if curl -s "http://${LOCAL_IP}:8080" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Launch browser
if command -v chromium-browser &> /dev/null; then
    chromium-browser --start-fullscreen "http://${LOCAL_IP}:8080" &
elif command -v firefox &> /dev/null; then
    firefox "http://${LOCAL_IP}:8080" &
elif command -v google-chrome &> /dev/null; then
    google-chrome --start-fullscreen "http://${LOCAL_IP}:8080" &
else
    # Fallback to default browser
    xdg-open "http://${LOCAL_IP}:8080" &
fi
EOF

# Make launch script executable
chmod +x launch_pibot.sh

echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo -e "${BLUE}🎉 PiBot Auto-Start Configuration:${NC}"
echo -e "   ✅ Systemd service installed and enabled"
echo -e "   ✅ Server will start automatically at boot"
echo -e "   ✅ Browser will launch automatically on desktop login"
echo ""
echo -e "${YELLOW}🔧 Service Management Commands:${NC}"
echo -e "   Status:  ${GREEN}sudo systemctl status ollama-chatbot${NC}"
echo -e "   Stop:    ${RED}sudo systemctl stop ollama-chatbot${NC}"
echo -e "   Start:   ${GREEN}sudo systemctl start ollama-chatbot${NC}"
echo -e "   Restart: ${YELLOW}sudo systemctl restart ollama-chatbot${NC}"
echo -e "   Logs:    ${BLUE}sudo journalctl -u ollama-chatbot -f${NC}"
echo ""
echo -e "${YELLOW}🖥️  Desktop Auto-Launch:${NC}"
echo -e "   To disable: Remove ~/.config/autostart/pibot-browser.desktop"
echo -e "   To test: ./launch_pibot.sh"
echo ""
echo -e "${GREEN}🚀 Reboot your Pi to test the full auto-start setup!${NC}"
