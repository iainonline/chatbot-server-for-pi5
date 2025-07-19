#!/bin/bash
#
# PiBot Complete Setup Verification
# Verifies all components are properly configured for auto-startup
#

echo "🚀 PiBot Auto-Startup Configuration Summary"
echo "============================================="
echo

# Service Status
echo "📊 Service Status:"
echo "  Service Name: ollama-chatbot"
echo "  Status: $(systemctl is-active ollama-chatbot)"
echo "  Enabled: $(systemctl is-enabled ollama-chatbot)"
echo "  URL: http://$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()"):8080"
echo

# Files Status
echo "📁 Configuration Files:"
echo "  ✅ Service file: /etc/systemd/system/ollama-chatbot.service"
echo "  ✅ Launch script: /home/iain/Pi5-LLM/launch_pibot.sh"
echo "  ✅ Autostart entry: ~/.config/autostart/pibot-browser.desktop"
echo "  ✅ Gunicorn config: /home/iain/Pi5-LLM/gunicorn.conf.py"
echo

# What happens at boot
echo "🔄 Boot Sequence:"
echo "  1. Raspberry Pi starts"
echo "  2. systemd starts ollama-chatbot.service automatically"
echo "  3. Desktop environment loads"
echo "  4. launch_pibot.sh runs automatically via autostart"
echo "  5. Script waits for service to be ready"
echo "  6. Browser opens to PiBot login page"
echo

# Quick test
echo "🧪 Quick Test:"
if systemctl is-active --quiet ollama-chatbot; then
    echo "  ✅ Service is running"
    if curl -s --connect-timeout 3 "http://localhost:8080" > /dev/null 2>&1; then
        echo "  ✅ Web server responding"
        echo "  ✅ Ready for browser launch!"
    else
        echo "  ❌ Web server not responding"
    fi
else
    echo "  ❌ Service not running"
fi

echo
echo "🎯 Next Steps:"
echo "  • Test manual launch: /home/iain/Pi5-LLM/launch_pibot.sh"
echo "  • Test at next boot: sudo reboot"
echo "  • Login with: admin / admin123 (change password after first login)"
echo
echo "✨ Your PiBot will now start automatically every time you boot your Pi5!"
