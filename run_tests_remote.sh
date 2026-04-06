#!/bin/bash
cd ~/openEtruscan
source venv/bin/activate
echo "Installing dependencies..." > execution_log.txt
python3 -m pip install -e .[server] pytest pytest-asyncio httpx aiosqlite >> execution_log.txt 2>&1
echo "Running pytest..." >> execution_log.txt
PYTHONPATH=src python3 -m pytest tests/test_server.py tests/test_corpus.py >> execution_log.txt 2>&1
echo "Running Pleiades alignment..." >> execution_log.txt
PYTHONPATH=src python3 scripts/ops/align_pleiades.py >> execution_log.txt 2>&1
echo "DONE" >> execution_log.txt
