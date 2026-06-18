#!/bin/bash
uv run main.py "$@" && /mnt/c/Python313/python.exe outlook_send.py
