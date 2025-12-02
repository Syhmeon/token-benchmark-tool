# Token Listing FDV Benchmark Tool - Contexte et Méthodologie

## 🎯 Objectif Principal

Créer un outil pour déterminer la **FDV (Fully Diluted Valuation) au lancement** de tokens crypto afin de :
- Benchmarker les valorisations par catégorie/narrative
- Comparer avec le capital levé (FDV/Raised ratio)
- Aider à valoriser de futurs lancements de tokens

---

## 📊 Méthodologie de Calcul du Prix Initial

### Le Problème Identifié

Les premières bougies CEX montrent souvent :
- **Test trades** à des prix aberrants ($0.03 pour JTO)
- **Wicks extrêmes** dépassant l'ATH (Bybit JTO: $32 vs ATH réel $5.91)
- **H/L ratio > 100x** dans la première minute

**Conclusion** : Le prix OPEN de la première bougie n'est PAS fiable pour le benchmark.

### Solution : Prix de Stabilisation DEX

1. **Collecter données multi-sources** :
   - CEX via CCXT (Binance, Bybit, OKX, Bitget, KuCoin, Gate.io)
   - DEX via Flipside (Orca, Raydium, Jupiter, Phoenix, Meteora)

2. **Identifier la stabilisation** :
   - Moment où plusieurs DEX convergent à ±1% spread
   - Typiquement 1-3h après TGE

3. **Prix de référence** = Moyenne pondérée des DEX à la stabilisation

### Exemple JTO

| Heure | Source | Prix | Fiabilité |
|-------|--------|------|-----------|
| 16:00 | Bybit OPEN | $0.03 | ❌ Test trade |
| 16:00 | Bybit HIGH | $3.00 | ⚠️ TGE volatil |
| 16:06 | Bybit HIGH | $32.67 | ❌ Wick impossible |
| 18:00 | DEX Orca | $2.035 | ✅ Stabilisé |
| 18:00 | DEX Phoenix | $2.036 | ✅ Stabilisé |
| 18:00 | DEX Raydium | $2.033 | ✅ Stabilisé |

**Prix Benchmark JTO** : $2.035 (convergence DEX +2h)
**FDV Benchmark JTO** : $2.035B

---

## 🔧 Architecture Technique

### Sources de Données

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                             │
├─────────────────────────────────────────────────────────────┤
│  CEX (via CCXT)           │  DEX (via Flipside MCP)         │
│  - Binance                │  - Orca Whirlpool (Solana)      │
│  - Bybit                  │  - Raydium (Solana)             │
│  - OKX                    │  - Jupiter (Solana)             │
│  - Bitget                 │  - Uniswap (Ethereum)           │
│  - KuCoin                 │  - Curve (Ethereum)             │
│  - Gate.io                │  - etc.                         │
├─────────────────────────────────────────────────────────────┤
│                  AUTRES SOURCES                              │
│  - CoinGecko : Supply, metadata, catégories                 │
│  - CryptoRank : Fundraising, allocations                    │
│  - ICODrops : Tokenomics, vesting                           │
│  - Messari : Fundraising rounds                             │
└─────────────────────────────────────────────────────────────┘
```

### Flux de Traitement

```
1. INPUT: Token symbol/CoinGecko ID
   │
2. RESOLVE: Metadata (supply, categories, blockchain)
   │
3. FETCH PRICES:
   ├── CEX via CCXT (bougies 1min)
   │   └── Filtrer: exclure H/L > 10x, prix > ATH
   │
   └── DEX via Flipside
       └── Requête SQL: avg_buy_price, avg_sell_price par heure
   │
4. DETECT STABILIZATION:
   │   Trouver première heure où spread < 1% entre DEX
   │
5. CALCULATE BENCHMARK:
   │   Prix = Moyenne pondérée DEX à stabilisation
   │   FDV = Total Supply × Prix
   │   MCap = Circulating TGE × Prix
   │
6. OUTPUT: Rapport JSON avec toutes sources et flags
```

---

## 📁 Structure des Fichiers

```
token_listing_tool/
├── src/
│   ├── core/
│   │   ├── models.py          # Pydantic models
│   │   ├── types.py           # Enums, types
│   │   └── exceptions.py      # Custom exceptions
│   │
│   ├── providers/
│   │   ├── price/
│   │   │   ├── ccxt_provider.py      # CEX data
│   │   │   ├── coingecko_price.py    # Fallback
│   │   │   └── flipside_provider.py  # DEX data (à créer)
│   │   │
│   │   ├── supply/
│   │   │   └── coingecko_supply.py
│   │   │
│   │   └── fundraising/
│   │       └── cryptorank_provider.py
│   │
│   ├── calculator/
│   │   ├── price_selector.py   # Sélection prix référence
│   │   └── valuation.py        # Calculs FDV/MCap
│   │
│   └── output/
│       └── formatters.py       # JSON, CSV, Table
│
├── config/
│   └── allocation_mapping.yaml  # Mapping buckets
│
├── examples/
│   ├── output/
│   │   └── jto_benchmark_report.json
│   └── analyze_listing_correct.py
│
└── .mcp.json                   # Config MCP Flipside
```

---

## 🎯 Tokens Analysés

### Résultats Préliminaires

| Token | Blockchain | TGE Date | Prix Benchmark | FDV | Source |
|-------|------------|----------|----------------|-----|--------|
| JTO | Solana | 2023-12-07 | $2.035 | $2.035B | DEX Flipside |
| EIGEN | Ethereum | 2024-10-01 | À calculer | - | CEX (pas DEX) |
| LAYER | Solana | 2025-02-11 | À calculer | - | - |
| 2Z | Solana | 2025-10-02 | À calculer | - | - |
| POND | Ethereum | 2020-12-22 | $0.16? | - | CEX ancien |
| PAL | Ethereum | 2022-03-25 | - | - | DEX only |
| FOLD | Ethereum | - | - | - | DEX only |
| 42 | BSC | 2025-10-27 | $0.11 | - | CEX BitMart |

### Tokens Non Listés
- RAI (Rakurai) : Pas encore de TGE
- BLXR (bloXroute) : Security token, pas public

---

## 🔑 APIs et Clés

### Flipside MCP
```
URL: https://mcp.flipsidecrypto.xyz/mcp
API Key: fv_MTZiYzJmYzgtYjJkMy00YWQ5LWI0ZGUtMWZhNmUyMDliMDg2
Status: Configuré, connecté
```

### CCXT
- Pas de clé requise pour données publiques
- Rate limits: ~30 calls/min par exchange

### CoinGecko
- Free tier: 10-30 calls/min
- Données: supply, metadata, historical prices (daily)

---

## 📝 Format de Sortie Recommandé

```json
{
  "token": {
    "symbol": "JTO",
    "name": "Jito",
    "blockchain": "Solana",
    "category": ["Liquid Staking", "MEV", "DeFi"]
  },
  "benchmark_valuation": {
    "reference_price_usd": 2.035,
    "price_method": "DEX convergence at stabilization",
    "fdv_usd": 2035000000,
    "mcap_usd": 234025000,
    "confidence": "HIGH"
  },
  "price_sources": {
    "cex_data": { /* toutes les bougies CEX avec flags */ },
    "dex_data": { /* prix DEX par heure avec volumes */ }
  },
  "fundraising": {
    "total_raised": 12100000,
    "fdv_to_raised": 168.2
  },
  "allocations": [ /* buckets avec vesting */ ],
  "sources": { /* URLs de toutes les sources */ }
}
```

---

## 🚀 Prochaines Étapes

1. **Activer MCP Flipside** : Restart Claude Code
2. **Créer flipside_provider.py** : Requêtes SQL automatisées
3. **Analyser EIGEN** : Token Ethereum (DEX Uniswap)
4. **Analyser LAYER, 2Z** : Tokens Solana récents
5. **Créer base de données** : SQLite ou JSON pour benchmark
6. **Interface CLI** : `python -m token_listing_tool analyze JTO`

---

## ⚠️ Points d'Attention

1. **Données CEX suspectes** : Toujours vérifier H/L ratio et comparer avec ATH
2. **Limites API** : Gate.io max 10000 bougies, certains CEX pas de data ancienne
3. **Tokens DEX-only** : PAL, FOLD - pas de données CEX fiables
4. **Différences horaires** : CEX peuvent lister à des heures différentes
5. **Ethereum vs Solana** : DEX différents (Uniswap vs Orca/Raydium)
