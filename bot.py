import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from web3 import Web3
import json
import asyncio
from typing import Dict, List, Set

# Chargement des variables d'environnement
load_dotenv()

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration Web3
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
if ALCHEMY_API_KEY:
    # Configuration Alchemy avec les bons headers
    ALCHEMY_URL = f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    provider = Web3.HTTPProvider(
        ALCHEMY_URL,
        request_kwargs={
            'headers': headers,
            'timeout': 30
        }
    )
    w3 = Web3(provider)
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

# Activer le middleware pour gérer les requêtes asynchrones
from web3.middleware import geth_poa_middleware
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

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
                    await check_new_transactions(address, config)
                    config.last_block = current_block
            await asyncio.sleep(1)  # Attendre 1 seconde entre chaque vérification
        except Exception as e:
            print(f"Erreur lors du monitoring: {e}")
            await asyncio.sleep(5)

async def check_new_transactions(address: str, config: TrackingConfig):
    # Logique pour vérifier les nouvelles transactions
    pass

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

@bot.command(name='test')
async def test_connection(ctx):
    """Teste la connexion à Base et la capacité à récupérer les données"""
    try:
        # Test de connexion basique
        is_connected = w3.is_connected()
        connection_msg = f"📡 Connexion au réseau: {'✅' if is_connected else '❌'}"
        
        # Test de récupération du dernier bloc
        try:
            latest_block = w3.eth.block_number
            block_msg = f"🔍 Dernier bloc: {latest_block}"
        except Exception as e:
            block_msg = f"❌ Erreur bloc: {str(e)}"
        
        # Test de récupération d'une transaction récente
        try:
            block = w3.eth.get_block('latest', full_transactions=True)
            if block and block.transactions:
                tx = block.transactions[0]
                tx_hash = tx['hash'].hex() if isinstance(tx, dict) else tx.hex()
                tx_msg = f"📝 Dernière transaction: {tx_hash}"
            else:
                tx_msg = "❌ Aucune transaction trouvée"
        except Exception as e:
            tx_msg = f"❌ Erreur transaction: {str(e)}"
            
        # Test de l'API Alchemy
        try:
            if ALCHEMY_API_KEY:
                alchemy_url = f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
                alchemy_w3 = Web3(Web3.HTTPProvider(alchemy_url))
                is_alchemy_connected = alchemy_w3.is_connected()
                alchemy_msg = f"🔌 Connexion Alchemy: {'✅' if is_alchemy_connected else '❌'}"
            else:
                alchemy_msg = "⚠️ Pas de clé Alchemy configurée"
        except Exception as e:
            alchemy_msg = f"❌ Erreur Alchemy: {str(e)}"
        
        # Envoyer le rapport
        status_report = f"""
**Test de Connexion Base**
{connection_msg}
{block_msg}
{tx_msg}
{alchemy_msg}

**Provider URL**: {w3.provider.endpoint_uri}
"""
        await ctx.send(status_report)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur lors du test: {str(e)}")

# Lancer le bot
bot.run(os.getenv('DISCORD_TOKEN')) 