# Données Collectées - Session Analyse

## JTO (Jito) - COMPLET ✅

### Prix CEX (CCXT)

**Bybit** - Premier à 16:00:00 UTC
```
Min 1:  O=$0.03   H=$3.00   C=$3.00   (H/L=100x) ⚠️ TGE
Min 2:  O=$3.00   H=$3.10   C=$3.00
Min 6:  O=$3.00   H=$10.61  C=$10.00  ⚠️ SUSPECT
Min 7:  O=$10.00  H=$32.67  C=$28.00  ❌ IMPOSSIBLE (ATH=$5.91)
```

**Binance** - 16:30:00 UTC (+30min retard)
```
Min 1:  O=$0.15   H=$4.94   C=$3.70   (H/L=32.9x) ⚠️ TGE
VWAP 1h: $2.31
Médiane CLOSE 1h: $2.13
```

### Prix DEX (Flipside) - Données User

**Heure 16:00-17:00** : Pas de prix (volatilité)

**Heure 18:00** (Stabilisation) :
| DEX | Avg Sell | Avg Buy | Swaps |
|-----|----------|---------|-------|
| Orca Whirlpool | $2.0359 | $2.0353 | 12,154 |
| Phoenix | $2.0357 | $2.0356 | 2,791 |
| Raydium CLMM | $2.0326 | $2.0348 | 2,913 |
| Jupiter v2 | $2.0357 | $2.0190 | 261 |
| Meteora DLMM | $2.0359 | $2.0349 | 1,543 |

**Prix convergence** : $2.035 ±0.5%

### Tokenomics
- Total Supply: 1,000,000,000
- TGE Circulating: 115,000,000 (11.5%)
- Airdrop: 10% (100M)
- Community/DAO: 24.3%
- Ecosystem: 25%
- Team: 24.5% (3yr vest, 1yr cliff)
- Investors: 16.2% (3yr vest, 1yr cliff)

### Fundraising
- Seed (Dec 2021): $2.1M
- Series A (Aug 2022): $10M
- Total: $12.1M

### FDV Benchmark
- Prix: $2.035
- FDV: $2.035B
- MCap TGE: $234M
- FDV/Raised: 168x

---

## EIGEN (EigenLayer) - PARTIEL

### Prix CEX (CCXT)
**Bitget** - 04:00:00 UTC (Premier)
```
O=$0.04  H=$5.00  C=$3.73  (H/L=125x) ⚠️ TGE
```

**Bybit** - 04:10:00 UTC
```
O=$0.30  H=$4.00  C=$3.43  (H/L=13.3x) ⚠️ TGE
```

**Binance** - 05:00:00 UTC
```
O=$0.30  H=$4.94  C=$4.00  (H/L=16.5x) ⚠️ TGE
```

### Tokenomics
- Total Supply: 1,770,084,115
- TGE Circulating: ~107M (6.05%)

### À FAIRE
- [ ] Récupérer données DEX Ethereum (Uniswap)
- [ ] Calculer prix stabilisation
- [ ] Compléter fundraising

---

## LAYER (Solayer) - PARTIEL

### Prix CEX (CCXT)
**Bybit** - 14:00:00 UTC (Feb 11, 2025)
```
O=$0.10  H=$1.15  C=$1.15  (H/L=11.5x) ⚠️ TGE
```

**Binance** - 14:00:00 UTC
```
O=$0.20  H=$1.36  C=$1.26  (H/L=6.8x) ⚠️ TGE
```

### À FAIRE
- [ ] Récupérer données DEX Solana
- [ ] Calculer prix stabilisation
- [ ] Tokenomics complets

---

## 2Z (DoubleZero) - PARTIEL

### Prix CEX (CCXT)
**Binance** - 13:00:00 UTC (Oct 2, 2025)
```
O=$0.05  H=$1.28  C=$0.82  (H/L=25.6x) ⚠️ TGE
```

**Bybit** - 13:00:00 UTC
```
O=$0.075  H=$1.11  C=$0.82  (H/L=14.8x) ⚠️ TGE
```

### À FAIRE
- [ ] Récupérer données DEX Solana
- [ ] Tokenomics complets

---

## POND (Marlin) - ANCIEN

### Prix CEX
**Huobi** - Dec 22, 2020 (Premier) : Données non disponibles (API limit)
**Binance** - Mar 9, 2021 : O=$0.16, pas de TGE candle (H/L=1.25x)

### Tokenomics
- Total Supply: 10,000,000,000
- Max Supply: 10,000,000,000

---

## 42 (Semantic Layer) - PARTIEL

### Prix CEX
**BitMart** - 11:00:00 UTC (Oct 27, 2025)
```
O=$0.11  H=$0.22  C=$0.22  (H/L=2.0x) - Pas TGE
```

---

## Tokens Non Analysables

| Token | Raison |
|-------|--------|
| PAL (Paladin) | DEX only, Gate.io data trop ancienne |
| FOLD (Manifold) | DEX only, pas sur CEX majeurs |
| RAI (Rakurai) | Pas encore listé |
| BLXR (bloXroute) | Security token, pas public |

---

## Configuration MCP Flipside

```
Server: flipside-crypto
URL: https://mcp.flipsidecrypto.xyz/mcp?apiKey=fv_MTZiYzJmYzgtYjJkMy00YWQ5LWI0ZGUtMWZhNmUyMDliMDg2
Status: Connected ✅
Requires: Restart Claude Code pour activer outils
```

## Requête Flipside SQL (exemple JTO)

```sql
SELECT
  DATE_TRUNC('hour', block_timestamp) as hour,
  swap_program,
  MIN(block_timestamp) as first_swap,
  AVG(CASE WHEN swap_from_mint = 'jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL'
      THEN swap_from_amount / swap_to_amount END) as avg_sell_price,
  AVG(CASE WHEN swap_to_mint = 'jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL'
      THEN swap_to_amount / swap_from_amount END) as avg_buy_price,
  COUNT(*) as swap_count
FROM solana.defi.ez_dex_swaps
WHERE block_timestamp >= '2023-12-07'
  AND block_timestamp < '2023-12-08'
  AND (swap_from_mint = 'jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL'
       OR swap_to_mint = 'jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL')
GROUP BY 1, 2
ORDER BY 1, 2
```
