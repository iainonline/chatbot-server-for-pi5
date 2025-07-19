#!/bin/bash
#
# PiBot Setup Verification Script
# Checks if everything is properly configured for auto-start
#

echo "🔍 PiBot Auto-Start Setup Verification"
echo "======================================"

# Check 1: Service file exists and is enabled
echo
echo "1. Checking systemd service..."
if systemctl is-enabled ollama-chatbot &>/dev/null; then
    echo "   ✅ Service is enabled for auto-start"
    if systemctl is-active ollama-chatbot &>/dev/null; then
        echo "   ✅ Service is currently running"
    else
        echo "   ❌ Service is not running"
        echo "   💡 Try: sudo systemctl start ollama-chatbot"
    fi
else
    echo "   ❌ Service is not enabled"
    echo "   💡 Try: sudo systemctl enable ollama-chatbot"
fi

# Check 2: Launch script exists and is executable
echo
echo "2. Checking launch script..."
if [ -x "/home/iain/Pi5-LLM/launch_pibot.sh" ]; then
    echo "   ✅ Launch script exists and is executable"
else
    echo "   ❌ Launch script is not executable"
    echo "   💡 Try: chmod +x /home/iain/Pi5-LLM/launch_pibot.sh"
fi

# Check 3: Autostart desktop entry exists
echo
echo "3. Checking autostart configuration..."
if [ -f "$HOME/.config/autostart/pibot-browser.desktop" ]; then
    echo "   ✅ Autostart desktop entry exists"
    
    # Check if the Exec path is correct
    if grep -q "/home/iain/Pi5-LLM/launch_pibot.sh" "$HOME/.config/autostart/pibot-browser.desktop"; then
        echo "   ✅ Desktop entry points to correct script"
    else
        echo "   ❌ Desktop entry has incorrect path"
    fi
else
    echo "   ❌ Autostart desktop entry not found"
    echo "   💡 Desktop entry should be at: $HOME/.config/autostart/pibot-browser.desktop"
fi

# Check 4: Network connectivity
echo
echo "4. Checking network connectivity..."
if ping -c 1 8.8.8.8 &>/dev/null; then
    echo "   ✅ Internet connectivity available"
else
    echo "   ❌ No internet connectivity"
    echo "   💡 Check network configuration"
fi

# Check 5: Web server response
echo
echo "5. Checking web server response..."
local_ip=$(python3 -c "
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

if curl -s --connect-timeout 3 "http://${local_ip}:8080" >/dev/null; then
    echo "   ✅ Web server is responding on http://${local_ip}:8080"
else
    echo "   ❌ Web server is not responding"
    echo "   💡 Check if the service is running properly"
fi

# Check 6: Browser availability
echo
echo "6. Checking browser availability..."
if command -v chromium-browser >/dev/null; then
    echo "   ✅ Chromium browser found"
elif command -v firefox >/dev/null; then
    echo "   ✅ Firefox browser found"
elif command -v x-www-browser >/dev/null; then
    echo "   ✅ Default browser found"
else
    echo "   ❌ No suitable browser found"
    echo "   💡 Install a browser: sudo apt install chromium-browser"
fi

echo
echo "======================================"
echo "📋 Summary:"
echo "   Service: $(systemctl is-active ollama-chatbot 2>/dev/null || echo 'inactive')"
echo "   Enabled: $(systemctl is-enabled ollama-chatbot 2>/dev/null || echo 'disabled')"
echo "   URL: http://${local_ip}:8080"
echo
echo "🔄 To test auto-launch manually:"
echo "   /home/iain/Pi5-LLM/launch_pibot.sh"
echo
echo "🚀 To test at next boot:"
echo "   sudo reboot"
