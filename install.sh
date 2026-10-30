#!/usr/bin/env bash
# One-command installer: deps, logger service, and sys-check alias in bashrc/zshrc.
# Usage: ./install.sh   (run from system-monitor directory)
# Optional: export FORTRESS_HOME=~/fortress before install if PlainTop should integrate with Fortress control.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPLAY_SCRIPT="$SCRIPT_DIR/display_stats.py"
PLAINTOP_SCRIPT="$SCRIPT_DIR/plaintop.py"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# 1) Install system deps (Debian/Ubuntu; adapt for Fedora/Arch if needed)
if command -v apt-get &>/dev/null; then
    echo "Installing system packages (lm-sensors, python3-venv)..."
    sudo apt-get update -qq
    sudo apt-get install -y lm-sensors python3-venv
    # Optional: run sensors-detect non-interactively to probe (nct6775 etc.)
    if [ -t 0 ]; then
        echo "Run 'sudo sensors-detect' once to probe MSI/nct6775 if temps are missing."
    fi
fi

# 2) Create venv and install Python deps (avoids PEP 668 externally-managed-environment)
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi
echo "Installing Python packages (rich, psutil, textual) into venv..."
"$VENV_PYTHON" -m pip install --quiet --upgrade pip
"$VENV_PYTHON" -m pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

ALIAS_LINE="alias sys-check='$VENV_PYTHON $DISPLAY_SCRIPT'"
PLAINTOP_ALIAS="alias plaintop='$VENV_PYTHON $PLAINTOP_SCRIPT'"

# 3) Background logger service (uses venv Python)
echo "Setting up systemd user service for power logger..."
PYTHON="$VENV_PYTHON" "$SCRIPT_DIR/setup_service.sh"

# 4) Alias in .bashrc
if [ -f "$HOME/.bashrc" ]; then
    if grep -q "sys-check" "$HOME/.bashrc" 2>/dev/null; then
        echo "Alias sys-check already present in ~/.bashrc"
    else
        echo "" >> "$HOME/.bashrc"
        echo "# system-monitor: one-command health check" >> "$HOME/.bashrc"
        echo "$ALIAS_LINE" >> "$HOME/.bashrc"
        echo "Appended sys-check alias to ~/.bashrc"
    fi
    if grep -q "plaintop" "$HOME/.bashrc" 2>/dev/null; then
        echo "Alias plaintop already present in ~/.bashrc"
    else
        echo "$PLAINTOP_ALIAS" >> "$HOME/.bashrc"
        echo "Appended plaintop alias to ~/.bashrc"
    fi
fi

# 5) Alias in .zshrc if it exists
if [ -f "$HOME/.zshrc" ]; then
    if grep -q "sys-check" "$HOME/.zshrc" 2>/dev/null; then
        echo "Alias sys-check already present in ~/.zshrc"
    else
        echo "" >> "$HOME/.zshrc"
        echo "# system-monitor: one-command health check" >> "$HOME/.zshrc"
        echo "$ALIAS_LINE" >> "$HOME/.zshrc"
        echo "Appended sys-check alias to ~/.zshrc"
    fi
    if grep -q "plaintop" "$HOME/.zshrc" 2>/dev/null; then
        echo "Alias plaintop already present in ~/.zshrc"
    else
        echo "$PLAINTOP_ALIAS" >> "$HOME/.zshrc"
        echo "Appended plaintop alias to ~/.zshrc"
    fi
fi

# 6) Reload shell config so it works in this session
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    # shellcheck source=/dev/null
    . "$HOME/.bashrc" 2>/dev/null || true
fi
if [ -n "$ZSH_VERSION" ] && [ -f "$HOME/.zshrc" ]; then
    # shellcheck source=/dev/null
    . "$HOME/.zshrc" 2>/dev/null || true
fi

echo ""
echo "Done. From any terminal (new or after sourcing config), run:"
echo "  sys-check   # one-shot snapshot"
echo "  plaintop    # live plain-English monitor (q to quit)"
