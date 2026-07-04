#!/bin/bash
# Automates the setup of the virtual environment and enforces .pycache directory

echo "Creating virtual environment..."
python3 -m venv venv

echo "Patching venv/bin/activate for PYTHONPYCACHEPREFIX..."
# Add teardown to deactivate
sed -i.bak '/unset VIRTUAL_ENV_PROMPT/a\
\
    if [ -n "${_OLD_VIRTUAL_PYTHONPYCACHEPREFIX:-}" ] ; then\
        PYTHONPYCACHEPREFIX="${_OLD_VIRTUAL_PYTHONPYCACHEPREFIX:-}"\
        export PYTHONPYCACHEPREFIX\
        unset _OLD_VIRTUAL_PYTHONPYCACHEPREFIX\
    else\
        unset PYTHONPYCACHEPREFIX\
    fi\
' venv/bin/activate

# Add setup to the end of activate
cat << 'EOF' >> venv/bin/activate

if [ -n "${PYTHONPYCACHEPREFIX:-}" ] ; then
    _OLD_VIRTUAL_PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-}"
fi
export PYTHONPYCACHEPREFIX="$(dirname "$VIRTUAL_ENV")/.pycache"
EOF

# Clean up sed backup
rm -f venv/bin/activate.bak

echo "Installing requirements..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Done! You can now run: source venv/bin/activate"
