# IBKR Patrimonial Bot

## Objectif
Bot d'accumulation patrimoniale autonome — achat progressif d'actions Wide Moat + Dividend Kings/Aristocrats via IBKR, déployé sur NAS UGREEN DXP4800 Plus (Docker).

## Stack
- **Runtime** : Python 3.12 + Docker (NAS UGREEN / Portainer)
- **Broker** : TWS API via `ib_insync` (pas Web API — cashQty/fractions non supportés)
- **Gateway** : `ghcr.io/gnzsnz/ib-gateway:stable` (login auto, ports 4001 live / 4002 paper)
- **Data** : `yfinance` batch download daily (1 req/jour, period=2y)
- **Indicateurs** : RSI(14) + MM200 en pandas pur
- **Alertes** : Telegram Bot (boutons inline OUI/NON/REPORTER)

## Architecture fichiers
```
/
├── docker-compose.yml
├── Dockerfile
├── watchlist.json          # 80 tickers (ticker, exchange, currency, sector, type)
├── .env                    # secrets (jamais committé)
├── src/
│   ├── main.py             # cron 22h30 + orchestration
│   ├── ibkr.py             # wrapper ib_insync (connect, cash, portfolio, order)
│   ├── indicators.py       # yfinance batch + RSI(14) + MM200
│   ├── scanner.py          # boucle watchlist, applique filtres, retourne signaux
│   └── telegram_bot.py     # bot Telegram + boutons inline + pending.json
└── data/
    └── pending.json        # signaux reportés (re-alerte J+1 si toujours valide)
```

## Stratégie d'achat
Toutes conditions simultanées :
1. RSI(14) daily < 30
2. Prix ≤ MM200 + 2%
3. Cash disponible > 50€

Sizing :
- `montant_cible = portefeuille_total × 1%`
- `montant_ordre = min(montant_cible, cash_disponible × 90%)`
- Si `montant_ordre < 10€` → pas d'alerte

Pas de sortie automatique.

## Flux d'exécution
```
Cron 22h30 (marchés fermés)
  → yfinance batch (80 tickers)
  → Calcul RSI + MM200 (pandas)
  → Pour chaque signal :
      → Vérif cash via ib_insync
      → Calcul montant_ordre
      → Si ≥ 10€ → alerte Telegram
          ✅ OUI → ordre cashQty via ib_insync
          ❌ NON → ignoré
          ⏳ REPORTER → re-alerte J+1
```

## Conventions de code
- Python 3.12, type hints sur les signatures publiques
- Logging via `logging` stdlib (pas de print)
- Config via variables d'environnement (`.env` + docker-compose)
- Pas de dépendances externes pour les calculs (pandas suffit)
- Gestion d'erreurs aux frontières : connexion IB, appels yfinance, API Telegram
- Retry avec backoff sur connexion IB Gateway (délai ~30s au démarrage)

## Commandes utiles
```bash
# Dev local (paper trading)
docker compose up -d
docker compose logs -f bot

# Tester la connexion IB Gateway
docker compose exec bot python -c "from ib_insync import IB; ib=IB(); ib.connect('ib-gateway',4002,clientId=1); print(ib.isConnected())"
```

## Règles importantes
- **Paper trading d'abord** : `TRADING_MODE=paper` + port 4002 jusqu'à validation complète
- **Jamais de `--force`** sur les ordres — toujours confirmation Telegram
- **Ne jamais committer** `.env`, credentials, tokens
- **IB Gateway** met ~30s à démarrer — le bot doit attendre avant de se connecter
- **pending.json** : re-alerter le lendemain uniquement si le signal est toujours valide (recalcul)

## Ordre de construction
1. `docker-compose.yml` + `Dockerfile`
2. `watchlist.json` (80 actions)
3. `src/ibkr.py`
4. `src/indicators.py`
5. `src/scanner.py`
6. `src/telegram_bot.py`
7. `src/main.py`
