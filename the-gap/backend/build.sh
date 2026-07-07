#!/usr/bin/env bash
set -e

pip install --upgrade pip

# Install numpy and pandas using only pre-built binary wheels
pip install --only-binary=:all: "numpy>=1.24,<2.0"
pip install --only-binary=:all: "pandas>=2.0,<3.0"

# Install remaining packages
pip install -r requirements.txt
