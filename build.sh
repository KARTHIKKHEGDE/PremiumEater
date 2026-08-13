#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt
# Playwright removed — cookies are now auto-fetched via curl_cffi (no browser needed)
