#!/bin/bash

VPN_CONFIG="./modbus.ovpn"

echo "Prüfe OpenVPN..."

if ! command -v openvpn >/dev/null 2>&1; then
    echo "OpenVPN ist nicht installiert."
    echo "Installation mit Homebrew:"
    echo "  brew install openvpn"
    exit 1
fi

if [ ! -f "$VPN_CONFIG" ]; then
    echo "VPN-Konfiguration nicht gefunden:"
    echo "  $VPN_CONFIG"
    exit 1
fi

echo "Starte OpenVPN..."
sudo openvpn --config "$VPN_CONFIG"
