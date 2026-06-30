#!/usr/bin/env bash
# exit on error
set -o errexit

# Instalează librăriile din Python
pip install -r requirements.txt

# Descarcă binarul Playwright în folderul local al aplicației, nu în cache-ul global
playwright install chromium