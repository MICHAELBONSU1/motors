#!/bin/bash
# StormerHost 1-Click Setup & Restart Script for BIG-L Autos
# This script installs all dependencies, initializes the database, and restarts the app.

set -e

echo "--------------------------------------------------------"
echo "  BIG-L Autos — StormerHost Automated Setup"
echo "--------------------------------------------------------"

# 1. Install & upgrade dependencies
echo "[1/4] Installing Python requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# 2. Initialize database (Admin Sarah Mitchell + Showroom Cars + WAL Mode)
echo "[2/4] Initializing database and ensuring persistence..."
python database.py

# 3. Create upload directory with proper permissions
echo "[3/4] Checking upload folder..."
mkdir -p static/uploads
chmod 755 static/uploads

# 4. Restart Phusion Passenger app automatically
echo "[4/4] Restarting Python application..."
mkdir -p tmp
touch tmp/restart.txt

echo "--------------------------------------------------------"
echo "  Setup Complete! Your BIG-L Autos application is LIVE."
echo "--------------------------------------------------------"
