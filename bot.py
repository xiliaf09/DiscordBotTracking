import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from web3 import Web3
import json
import asyncio
from typing import Dict, List, Set
from transaction_handler import TransactionHandler
from notification_handler import NotificationHandler

# Chargement des variables d'environnement
load_dotenv()

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration Web3 avec Alchemy
ALCHEMY_URL = "https://base-mainnet.g.alchemy.com/v2/" + os.getenv('ALCHEMY_API_KEY')
w3 = Web3(Web3.HTTPProvider(ALCHEMY_URL))

# Vérification de la connexion
if not w3.is_connected():
    raise Exception("Impossible de se connecter à Alchemy")
else:
    print("Connecté à Alchemy avec succès!")

# Initialisation des handlers
tx_handler = TransactionHandler(w3)
notif_handler = NotificationHandler(bot)

# Structure de données pour stocker les configurations de tracking
tracking_configs: Dict[str, Dict] = {}

class TrackingConfig:
    def __init__(self, address: str, channel_id: int, filters: Dict = None):
        self.address = address.lower()
        self.channel_id = channel_id
        self.filters = filters or {}
        self.last_block = w3.eth.block_number

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté et prêt!')
    # Démarrer la tâche de monitoring
    bot.loop.create_task(monitor_addresses())

async def monitor_addresses():
    while True:
        try:
            current_block = w3.eth.block_number
            for address, config in tracking_configs.items():
                if current_block > config.last_block:
                    # Vérifier les nouvelles transactions
                    transactions = await get_new_transactions(address, config.last_block, current_block)
                    for tx in transactions:
                        tx_info = await tx_handler.process_transaction(tx, config)
                        if tx_info:
                            await notif_handler.send_notification(config.channel_id, tx_info)
                    config.last_block = current_block
            await asyncio.sleep(1)  # Attendre 1 seconde entre chaque vérification
        except Exception as e:
            print(f"Erreur lors du monitoring: {e}")
            await asyncio.sleep(5)

async def get_new_transactions(address: str, from_block: int, to_block: int) -> List[str]:
    """Récupère les nouvelles transactions pour une adresse"""
    # Rechercher les transactions où l'adresse est émetteur
    from_filter = w3.eth.filter({
        'fromBlock': from_block,
        'toBlock': to_block,
        'fromAddress': address
    })
    
    # Rechercher les transactions où l'adresse est destinataire
    to_filter = w3.eth.filter({
        'fromBlock': from_block,
        'toBlock': to_block,
        'toAddress': address
    })
    
    # Combiner les résultats
    from_txs = await from_filter.get_all_entries()
    to_txs = await to_filter.get_all_entries()
    
    # Extraire les hashes de transaction uniques
    tx_hashes = set()
    for tx in from_txs + to_txs:
        tx_hashes.add(tx['transactionHash'].hex())
    
    return list(tx_hashes)

@bot.command(name='track')
async def track_address(ctx, address: str, *, filters: str = None):
    """Ajouter une adresse à tracker"""
    try:
        if not w3.is_address(address):
            await ctx.send("❌ Adresse invalide")
            return

        # Parser les filtres si fournis
        filter_dict = {}
        if filters:
            try:
                filter_dict = json.loads(filters)
            except json.JSONDecodeError:
                await ctx.send("❌ Format de filtres invalide")
                return

        tracking_configs[address.lower()] = TrackingConfig(
            address=address.lower(),
            channel_id=ctx.channel.id,
            filters=filter_dict
        )
        
        await ctx.send(f"✅ Adresse {address} ajoutée au tracking")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='untrack')
async def untrack_address(ctx, address: str):
    """Retirer une adresse du tracking"""
    address = address.lower()
    if address in tracking_configs:
        del tracking_configs[address]
        await ctx.send(f"✅ Adresse {address} retirée du tracking")
    else:
        await ctx.send("❌ Adresse non trouvée dans le tracking")

@bot.command(name='list')
async def list_tracked(ctx):
    """Lister toutes les adresses trackées"""
    if not tracking_configs:
        await ctx.send("Aucune adresse trackée")
        return

    message = "📋 Adresses trackées:\n"
    for address, config in tracking_configs.items():
        message += f"- {address}\n"
        if config.filters:
            message += f"  Filtres: {json.dumps(config.filters, indent=2)}\n"
    
    await ctx.send(message)

# Lancer le bot
bot.run(os.getenv('DISCORD_TOKEN')) 