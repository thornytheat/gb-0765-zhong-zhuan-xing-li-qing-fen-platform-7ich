from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / 'sample_data'
FILES = ('scans.csv', 'legs.csv', 'manifest.csv', 'carts.csv', 'receipts.csv')
STAGES = ('scans', 'legs', 'loading', 'replay', 'exceptions', 'ledger')
VERSION = 'leg-luggage/2'
