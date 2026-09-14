#!/usr/bin/env bash
# Install the project dependencies
set -euo pipefail

install_link="https://pixi.sh/install.sh"
echo "Installing Pixi..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL ${install_link}| sh
elif command -v wget >/dev/null 2>&1; then
    wget -qO- ${install_link} | sh
else
    echo "curl or wget is required to install Pixi." >&2
    exit 1
fi

export PATH="$HOME/.pixi/bin:$PATH"

pixi update
pixi run setup-sby
pixi run setup-bender
bender update
