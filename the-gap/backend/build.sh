#!/usr/bin/env bash
set -e

pip install --upgrade pip

# Install numpy and pandas using only pre-built binary wheels
# This prevents source compilation which runs out of memory on free tier
pip install --only-binary=:all: "numpy>=1.26,<2.0"
pip install --only-binary=:all: "pandas>=2.0,<3.0"

# Install remaining packages
pip install -r requirements.txt
