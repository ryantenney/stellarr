#!/bin/bash

# Overseer Lite - Let's Encrypt SSL Certificate Setup Script
# This script initializes SSL certificates using Let's Encrypt

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check required variables
if [ -z "$DOMAIN" ]; then
    echo "Error: DOMAIN is not set. Please set it in .env file."
    exit 1
fi

if [ -z "$EMAIL" ]; then
    echo "Error: EMAIL is not set. Please set it in .env file."
    exit 1
fi

# Staging flag (use staging for testing to avoid rate limits)
STAGING=${LETSENCRYPT_ENV:-production}
if [ "$STAGING" = "staging" ]; then
    STAGING_ARG="--staging"
    echo "Using Let's Encrypt staging environment (for testing)"
else
    STAGING_ARG=""
    echo "Using Let's Encrypt production environment"
fi

# Create directories
mkdir -p ./certbot/conf
mkdir -p ./certbot/www

# Download recommended TLS parameters
if [ ! -e "./certbot/conf/options-ssl-nginx.conf" ]; then
    echo "Downloading recommended TLS parameters..."
    curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "./certbot/conf/options-ssl-nginx.conf"
    curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "./certbot/conf/ssl-dhparams.pem"
fi

# Create dummy certificate for initial nginx startup
echo "Creating dummy certificate for $DOMAIN..."
CERT_PATH="./certbot/conf/live/$DOMAIN"
mkdir -p "$CERT_PATH"

docker run --rm \
    -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
    certbot/certbot \
    certonly --standalone \
    --register-unsafely-without-email \
    --agree-tos \
    -d "$DOMAIN" \
    $STAGING_ARG \
    --dry-run || {
        # Generate self-signed cert for initial startup
        openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
            -keyout "$CERT_PATH/privkey.pem" \
            -out "$CERT_PATH/fullchain.pem" \
            -subj "/CN=$DOMAIN"
    }

# Start nginx
echo "Starting nginx..."
docker compose -f docker-compose.ssl.yml up -d nginx

# Wait for nginx to start
sleep 5

# Delete dummy certificate
echo "Deleting dummy certificate..."
rm -rf "./certbot/conf/live/$DOMAIN"
rm -rf "./certbot/conf/archive/$DOMAIN"
rm -rf "./certbot/conf/renewal/$DOMAIN.conf"

# Request real certificate
echo "Requesting Let's Encrypt certificate for $DOMAIN..."
docker run --rm \
    -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/certbot/www:/var/www/certbot" \
    certbot/certbot \
    certonly --webroot \
    -w /var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    $STAGING_ARG

# Reload nginx
echo "Reloading nginx..."
docker compose -f docker-compose.ssl.yml exec nginx nginx -s reload

echo ""
echo "=========================================="
echo "SSL certificate setup complete!"
echo "=========================================="
echo ""
echo "Your site should now be accessible at:"
echo "  https://$DOMAIN"
echo ""
echo "Certificate will auto-renew via certbot container."
