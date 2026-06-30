#!/usr/bin/env bash
# exit on error
set -o errexit

# Instalează librăriile din Python
pip install -r requirements.txt

# Forțează instalarea browserului în folderul local al proiectului
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/.local-browsers
playwright install chromium