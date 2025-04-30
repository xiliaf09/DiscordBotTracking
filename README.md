# Bot de Tracking On-Chain Base

Ce bot Discord permet de tracker les transactions on-chain sur le réseau Base en temps réel.

## Fonctionnalités

- Tracking en temps réel des transactions
- Support des transferts ETH
- Support des transferts de tokens ERC20
- Support des interactions avec les smart contracts
- Filtres personnalisables par adresse
- Notifications claires et détaillées via Discord

## Installation

1. Clonez ce repository
2. Installez les dépendances :
```bash
pip install -r requirements.txt
```

3. Créez un fichier `.env` à la racine du projet avec vos tokens :
```
DISCORD_TOKEN=votre_token_discord_ici
ALCHEMY_API_KEY=votre_cle_api_alchemy_ici
```

4. Pour obtenir les tokens :
   - Discord Token : Créez une application sur le [Discord Developer Portal](https://discord.com/developers/applications)
   - Alchemy API Key : Créez un compte sur [Alchemy](https://www.alchemy.com/) et créez une nouvelle app pour Base

5. Lancez le bot :
```bash
python bot.py
```

## Commandes

- `!track <adresse> [filtres]` : Ajouter une adresse à tracker
  - Exemple : `!track 0x123...`
  - Avec filtres : `!track 0x123... {"token_address": "0x456...", "min_amount": 1.0}`

- `!untrack <adresse>` : Retirer une adresse du tracking
  - Exemple : `!untrack 0x123...`

- `!list` : Lister toutes les adresses trackées

## Filtres disponibles

- `token_address` : Adresse du token à tracker
- `min_amount` : Montant minimum pour déclencher une notification

## Format des notifications

Les notifications incluent :
- Type de transaction
- Statut (succès/échec)
- Montant (pour les transferts ETH)
- Informations sur le token (pour les transferts de tokens)
- Liens vers Basescan
- Adresses source et destination 