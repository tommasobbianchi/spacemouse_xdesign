#!/bin/bash
set -e

# Detect User and Home
if [ "$EUID" -eq 0 ]; then
    if [ -n "$SUDO_USER" ]; then
        REAL_USER="$SUDO_USER"
        REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    else
        echo "Please do not run as root directly. Use: sudo ./setup_ssl.sh"
        exit 1
    fi
else
    # Re-run with sudo if needed for system commands, but generally we want to start as user
    # Actually, simpler: Require running as User, use sudo internally for specific commands
    REAL_USER="$USER"
    REAL_HOME="$HOME"
fi

# Config
CERT_DIR="$REAL_HOME/.config/spacemouse-bridge"
CA_KEY="$CERT_DIR/rootCA.key"
CA_CERT="$CERT_DIR/rootCA.pem"
SERVER_KEY="$CERT_DIR/key.pem"
SERVER_CERT="$CERT_DIR/cert.pem" # main.py expects this
CONFIG_FILE="$CERT_DIR/openssl.cnf"

echo "=== SpaceMouse Bridge SSL Setup ==="
echo "Target Directory: $CERT_DIR"
echo "We need 'sudo' privileges to install tools and update system trust."
echo ""

# 1. Install Dependencies
echo "[1/5] Checking dependencies..."
if ! command -v certutil &> /dev/null; then
    echo "Installing libnss3-tools..."
    sudo apt-get update
    sudo apt-get install -y libnss3-tools
else
    echo "certutil found."
fi

mkdir -p "$CERT_DIR"
chown "$REAL_USER:$REAL_USER" "$CERT_DIR"

# 2. Generate Root CA
echo "[2/5] Generating Root CA..."
if [ ! -f "$CA_CERT" ]; then
    openssl genrsa -out "$CA_KEY" 2048
    openssl req -x509 -new -nodes -key "$CA_KEY" -sha256 -days 3650 -out "$CA_CERT" -subj "/CN=SpaceMouse Bridge Local Root CA"
    
    # Fix permissions
    chown "$REAL_USER:$REAL_USER" "$CA_KEY" "$CA_CERT"
    chmod 600 "$CA_KEY"
    echo "Root CA generated."
else
    echo "Root CA already exists. reusing."
fi

# 3. Trust Root CA
echo "[3/5] Trusting Root CA..."

# Chrome / Chromium (NSS DB)
echo "Adding to Chrome/NSS Database ($REAL_HOME/.pki/nssdb)..."
mkdir -p "$REAL_HOME/.pki/nssdb"
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.pki"
chmod 700 "$REAL_HOME/.pki"

# Create/Update DB (Run as User, not Root, to own the DB files)
sudo -u "$REAL_USER" certutil -d sql:"$REAL_HOME/.pki/nssdb" -N --empty-password 2>/dev/null || true
# Delete old if exists to update
sudo -u "$REAL_USER" certutil -d sql:"$REAL_HOME/.pki/nssdb" -D -n "SpaceMouse Local CA" 2>/dev/null || true
# Add
sudo -u "$REAL_USER" certutil -d sql:"$REAL_HOME/.pki/nssdb" -A -t "C,," -n "SpaceMouse Local CA" -i "$CA_CERT"
echo "Trusted in Chrome/NSS."

# System Store
echo "Adding to System Trust Store..."
sudo cp "$CA_CERT" /usr/local/share/ca-certificates/spacemouse-root-ca.crt
sudo update-ca-certificates

# 4. Generate Server Certificate
echo "[4/5] Generating Server Certificate..."
# Create config for SAN (Subject Alternative Names)
cat > "$CONFIG_FILE" <<EOF
[req]
req_extensions = req_ext
distinguished_name = dn
prompt = no

[dn]
CN = localhost

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
IP.2 = 127.51.68.120
IP.3 = ::1
EOF

# Generate Server Key & CSR
openssl genrsa -out "$SERVER_KEY" 2048
openssl req -new -key "$SERVER_KEY" -out "$CERT_DIR/server.csr" -config "$CONFIG_FILE"

# Sign with Root CA
openssl x509 -req -in "$CERT_DIR/server.csr" -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
    -out "$SERVER_CERT" -days 365 -sha256 -extfile "$CONFIG_FILE" -extensions req_ext

# Fix file permissions
chown "$REAL_USER:$REAL_USER" "$SERVER_KEY" "$SERVER_CERT" "$CONFIG_FILE" "$CERT_DIR/server.csr" "$CERT_DIR/rootCA.srl" 2>/dev/null || true

echo "[5/5] Done!"
echo "Please restart Chrome/xDesign and the SpaceMouse service."
echo ""

