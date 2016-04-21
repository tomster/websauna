#!/bin/bash
#
# Create wheelhouse cache to speed up test_scaffold runs.
# Builds a wheelhouse folder containing al dependencies.
#

set -e
# set -x

if type virtualenv-3.4 ; then
    # OSX + Homebrew
    VIRTUALENV=virtualenv-3.4
    PYTHON_VERSION=python3.4
else
    VIRTUALENV=virtualenv
    # PYTHON_VERSION set by CI
fi


rm -rf /tmp/wheelhouse-venv
rm -rf wheelhouse/$PYTHON_VERSION
$VIRTUALENV -q --no-site-packages -p $PYTHON_VERSION /tmp/wheelhouse-venv
source /tmp/wheelhouse-venv/bin/activate
# default pip is too old for 3.4
pip install -q -U pip

# We do the messages three phases as otherwise Travis considers our build stalled after 10m and I hope this solves this
echo "Installing project core dependencies."

pip install -q .

echo "Installing project test dependencies."
pip install -q ".[test]"
echo "Installing project dev dependencies."
pip install -q ".[dev]"
pip install -q wheel
pip freeze > /tmp/wheelhouse-venv/requirements.txt

# websauna 0.0 lsdevelopment not available, remove from freeze
echo "$(grep -v "websauna" /tmp/wheelhouse-venv/requirements.txt)" >/tmp/wheelhouse-venv/requirements.txt

# Build wheelhouse
echo "Building wheelhouse"
pip wheel -q -r /tmp/wheelhouse-venv/requirements.txt --wheel-dir wheelhouse/$PYTHON_VERSION