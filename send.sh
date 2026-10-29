#!/bin/bash
uv run main.py "$@" && /mnt/c/Python313/python.exe send_from_staging.py
