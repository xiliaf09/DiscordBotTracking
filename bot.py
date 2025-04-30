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
from eth_utils import to_checksum_address

# Chargement des variables d'environnement
load_dotenv()

# Vérification des variables d'environnement requises
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN n'est pas défini dans les variables d'environnement")

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Configuration Web3
if ALCHEMY_API_KEY:
    # Essayer d'abord Alchemy
    ALCHEMY_URL = f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
    w3 = Web3(Web3.HTTPProvider(ALCHEMY_URL))
    print(f"Tentative de connexion à Alchemy...")
    
    if w3.is_connected():
        print(f"Connecté à Alchemy avec succès! Version de l'API: {w3.api}")
    else:
        print("Impossible de se connecter à Alchemy, utilisation du RPC public...")
        w3 = Web3(Web3.HTTPProvider('https://mainnet.base.org'))
else:
    print("Pas de clé Alchemy configurée, utilisation du RPC public...")
    w3 = Web3(Web3.HTTPProvider('https://mainnet.base.org'))

# Vérification finale de la connexion
if not w3.is_connected():
    raise Exception("Impossible de se connecter à un nœud Base")
else:
    print(f"Connecté au réseau Base! Dernier bloc: {w3.eth.block_number}")

# Initialisation des handlers
tx_handler = TransactionHandler(w3)
notif_handler = NotificationHandler(bot)

# Structure de données pour stocker les configurations de tracking
tracking_configs: Dict[str, Dict] = {}

class TrackingConfig:
    def __init__(self, address: str, channel_id: int, filters: Dict = None):
        self.address = to_checksum_address(address.lower())
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
            if not tracking_configs:
                print("Aucune adresse à tracker, attente...")
                await asyncio.sleep(5)
                continue

            current_block = w3.eth.block_number
            print(f"Vérification des transactions - Bloc actuel: {current_block}")
            
            for address, config in tracking_configs.items():
                print(f"Vérification de l'adresse {address} (dernier bloc vérifié: {config.last_block})")
                if current_block > config.last_block:
                    # Récupérer les transactions pour cette plage de blocs
                    from_block = config.last_block + 1
                    to_block = current_block
                    print(f"Recherche des transactions entre les blocs {from_block} et {to_block}")

                    # Vérifier les transactions envoyées
                    sent_txs = await get_transactions_for_address(address, from_block, to_block, 'from')
                    print(f"Transactions envoyées trouvées: {len(sent_txs)}")
                    
                    # Vérifier les transactions reçues
                    received_txs = await get_transactions_for_address(address, from_block, to_block, 'to')
                    print(f"Transactions reçues trouvées: {len(received_txs)}")
                    
                    # Traiter toutes les transactions
                    all_txs = sent_txs + received_txs
                    print(f"Total des transactions à traiter: {len(all_txs)}")
                    
                    for tx_hash in set(all_txs):  # Utiliser un set pour éviter les doublons
                        print(f"Traitement de la transaction: {tx_hash}")
                        tx_info = await tx_handler.process_transaction(tx_hash, config)
                        if tx_info:
                            print(f"Envoi de la notification pour la transaction {tx_hash} dans le channel {config.channel_id}")
                            await notif_handler.send_notification(config.channel_id, tx_info)
                        else:
                            print(f"Aucune information à notifier pour la transaction {tx_hash}")
                    
                    config.last_block = current_block
                else:
                    print(f"Pas de nouveaux blocs pour l'adresse {address}")

            await asyncio.sleep(1)  # Attendre 1 seconde entre chaque vérification
            
        except Exception as e:
            print(f"Erreur lors du monitoring: {str(e)}")
            await asyncio.sleep(5)

async def get_transactions_for_address(address: str, from_block: int, to_block: int, direction: str) -> List[str]:
    """Récupère les transactions pour une adresse dans une direction donnée"""
    try:
        print(f"Recherche des transactions {direction} pour l'adresse {address}")
        # Construire le filtre en fonction de la direction
        if direction == 'from':
            transactions = w3.eth.get_transaction_count(address, to_block) - w3.eth.get_transaction_count(address, from_block - 1)
            print(f"Nombre de transactions envoyées trouvées: {transactions}")
            if transactions > 0:
                block_transactions = []
                for block_num in range(from_block, to_block + 1):
                    print(f"Analyse du bloc {block_num}")
                    block = w3.eth.get_block(block_num, full_transactions=True)
                    for tx in block.transactions:
                        if isinstance(tx, dict) and tx['from'].lower() == address.lower():
                            block_transactions.append(tx['hash'].hex())
                            print(f"Transaction trouvée: {tx['hash'].hex()}")
                return block_transactions
        else:  # direction == 'to'
            block_transactions = []
            for block_num in range(from_block, to_block + 1):
                print(f"Analyse du bloc {block_num}")
                block = w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.transactions:
                    if isinstance(tx, dict) and tx.get('to', '').lower() == address.lower():
                        block_transactions.append(tx['hash'].hex())
                        print(f"Transaction trouvée: {tx['hash'].hex()}")
            return block_transactions
        
        return []
    except Exception as e:
        print(f"Erreur lors de la récupération des transactions ({direction}): {str(e)}")
        return []

@bot.command(name='track')
async def track_address(ctx, address: str, *, filters: str = None):
    """Ajouter une adresse à tracker"""
    try:
        if not w3.is_address(address):
            await ctx.send("❌ Adresse invalide")
            return

        # Convertir l'adresse en format checksum
        checksum_address = to_checksum_address(address.lower())
        
        # Parser les filtres si fournis
        filter_dict = {}
        if filters:
            try:
                filter_dict = json.loads(filters)
                # Convertir les adresses de token en format checksum si présentes
                if 'token_address' in filter_dict:
                    filter_dict['token_address'] = to_checksum_address(filter_dict['token_address'].lower())
            except json.JSONDecodeError:
                await ctx.send("❌ Format de filtres invalide")
                return

        tracking_configs[checksum_address] = TrackingConfig(
            address=checksum_address,
            channel_id=ctx.channel.id,
            filters=filter_dict
        )
        
        await ctx.send(f"✅ Adresse {checksum_address} ajoutée au tracking")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='untrack')
async def untrack_address(ctx, address: str):
    """Retirer une adresse du tracking"""
    try:
        checksum_address = to_checksum_address(address.lower())
        if checksum_address in tracking_configs:
            del tracking_configs[checksum_address]
            await ctx.send(f"✅ Adresse {checksum_address} retirée du tracking")
        else:
            await ctx.send("❌ Adresse non trouvée dans le tracking")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

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

@bot.command(name='help')
async def show_help(ctx):
    """Affiche l'aide du bot"""
    embed = discord.Embed(
        title="📚 Aide - Base Tracking Bot",
        description="Voici les commandes disponibles :",
        color=0x3498db
    )

    embed.add_field(
        name="!track <adresse> [filtres]",
        value="Commence à tracker une adresse. Optionnellement avec des filtres.\n"
              "Exemple: `!track 0x123... {\"token_address\": \"0x456...\", \"min_amount\": 1.0}`",
        inline=False
    )

    embed.add_field(
        name="!untrack <adresse>",
        value="Arrête de tracker une adresse.\n"
              "Exemple: `!untrack 0x123...`",
        inline=False
    )

    embed.add_field(
        name="!list",
        value="Affiche la liste des adresses actuellement trackées.",
        inline=False
    )

    embed.add_field(
        name="!help",
        value="Affiche ce message d'aide.",
        inline=False
    )

    embed.add_field(
        name="📝 Filtres disponibles",
        value="• `token_address`: Adresse du token à tracker\n"
              "• `min_amount`: Montant minimum pour déclencher une alerte",
        inline=False
    )

    await ctx.send(embed=embed)

# Lancer le bot
bot.run(DISCORD_TOKEN) 