#!/usr/bin/env python3
"""Verify JTO price data - check for anomalies."""

import ccxt
from datetime import datetime, timezone

bybit = ccxt.bybit({'enableRateLimit': True})
bybit.load_markets()

since = datetime(2023, 12, 7, 16, 0, 0, tzinfo=timezone.utc)
since_ms = int(since.timestamp() * 1000)

candles = bybit.fetch_ohlcv('JTO/USDT', '1m', since=since_ms, limit=30)

print('BYBIT JTO/USDT - 30 premières minutes')
print('='*60)
print(f'{"Min":<4} {"OPEN":<10} {"HIGH":<10} {"LOW":<10} {"CLOSE":<10}')
print('-'*60)

for i, c in enumerate(candles):
    ts = datetime.fromtimestamp(c[0]/1000, tz=timezone.utc)
    flag = " <-- SUSPECT!" if c[2] > 6.0 else ""
    print(f'{i+1:<4} ${c[1]:<9.4f} ${c[2]:<9.4f} ${c[3]:<9.4f} ${c[4]:<9.4f}{flag}')

print()
print(f'MAX HIGH dans les 30 min: ${max(c[2] for c in candles):.4f}')
print(f'ATH réel JTO selon CoinGecko: ~$5.91')
print()
print('NOTE: Si HIGH > $6, données Bybit potentiellement erronées ou wicks extrêmes')
