import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from web3 import Web3
import json
import asyncio
from typing import Dict, List, Set
import time
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, filename='tracking_data.json'):
        self.filename = filename
        self.data = self.load_data()

    def load_data(self) -> Dict:
        """Charge les données depuis le fichier JSON"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Erreur lors du chargement des données: {str(e)}")
            return {}

    def save_data(self, data: Dict):
        """Sauvegarde les données dans le fichier JSON"""
        try:
            with open(self.filename, 'w') as f:
                json.dump(data, f, indent=4)
            logger.info("Données sauvegardées avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des données: {str(e)}")

# Initialisation du gestionnaire de données
data_manager = DataManager()

# Chargement des variables d'environnement
load_dotenv()

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def setup_web3_connection(max_retries=3, retry_delay=5):
    """Configure la connexion Web3 avec retry pour Alchemy"""
    ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
    
    if not ALCHEMY_API_KEY:
        logger.warning("Pas de clé Alchemy configurée, utilisation du RPC public...")
        return Web3(Web3.HTTPProvider('https://mainnet.base.org'))

    for attempt in range(max_retries):
        try:
            logger.info(f"Tentative de connexion à Alchemy (essai {attempt + 1}/{max_retries})...")
            
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
            
            if w3.is_connected():
                # Test supplémentaire pour vérifier la connexion
                block = w3.eth.block_number
                logger.info(f"Connecté à Alchemy avec succès! Version de l'API: {w3.api}")
                logger.info(f"Dernier bloc: {block}")
                return w3
            
            logger.warning(f"Échec de la connexion à Alchemy (tentative {attempt + 1})")
            
        except Exception as e:
            logger.error(f"Erreur lors de la connexion à Alchemy: {str(e)}")
        
        if attempt < max_retries - 1:
            logger.info(f"Nouvelle tentative dans {retry_delay} secondes...")
            time.sleep(retry_delay)
    
    logger.warning("Impossible de se connecter à Alchemy après plusieurs tentatives, utilisation du RPC public...")
    return Web3(Web3.HTTPProvider('https://mainnet.base.org'))

# Configuration Web3
w3 = setup_web3_connection()

# Vérification finale de la connexion
if not w3.is_connected():
    raise Exception("Impossible de se connecter à un nœud Base")

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
    # Charger les configurations sauvegardées
    global tracking_configs
    tracking_configs = data_manager.load_data()
    logger.info(f"Configurations chargées: {len(tracking_configs)} adresses")
    # Démarrer la tâche de monitoring
    bot.loop.create_task(monitor_addresses())

async def monitor_addresses():
    """Surveille les transactions pour les adresses trackées"""
    last_checked_block = {}
    
    while True:
        try:
            current_block = w3.eth.block_number
            logger.info(f"\n{'='*50}\nVérification du bloc {current_block}")
            
            for address in tracking_configs.keys():
                try:
                    # Conversion en checksum address
                    checksum_address = Web3.to_checksum_address(address)
                    
                    if address not in last_checked_block:
                        last_checked_block[address] = current_block - 1
                    
                    last_block = last_checked_block[address]
                    logger.info(f"\nVérification de l'adresse: {checksum_address}")
                    logger.info(f"Dernier bloc vérifié: {last_block}")
                    
                    # Vérification des transactions sortantes
                    current_nonce = w3.eth.get_transaction_count(checksum_address)
                    last_nonce = w3.eth.get_transaction_count(checksum_address, block_identifier=last_block)
                    
                    if current_nonce > last_nonce:
                        logger.info(f"Nouvelles transactions sortantes trouvées: {current_nonce - last_nonce}")
                        # Récupération des transactions
                        for block in range(last_block + 1, current_block + 1):
                            block_txs = w3.eth.get_block(block, True)['transactions']
                            for tx in block_txs:
                                if tx['from'].lower() == address.lower():
                                    await process_transaction(tx['hash'].hex(), address, is_outgoing=True)
                    
                    # Vérification des transactions entrantes via les logs
                    transfer_filter = w3.eth.filter({
                        'fromBlock': last_block + 1,
                        'toBlock': current_block,
                        'address': None,  # Tous les contrats
                        'topics': [None],  # Tous les événements
                    })
                    
                    for event in transfer_filter.get_all_entries():
                        if 'to' in event and event['to'].lower() == address.lower():
                            await process_transaction(event['transactionHash'].hex(), address, is_outgoing=False)
                    
                    last_checked_block[address] = current_block
                    
                except Exception as e:
                    logger.error(f"Erreur lors de la vérification de l'adresse {address}: {str(e)}")
                    continue
            
            await asyncio.sleep(12)  # Attente entre les vérifications
            
        except Exception as e:
            logger.error(f"Erreur dans la boucle de monitoring: {str(e)}")
            await asyncio.sleep(30)  # Attente plus longue en cas d'erreur

async def check_new_transactions(address: str, config: TrackingConfig):
    # Logique pour vérifier les nouvelles transactions
    pass

@bot.command(name='track')
async def track_address(ctx, address: str, *args):
    """Tracker une adresse avec des filtres optionnels"""
    try:
        # Valider l'adresse
        if not w3.is_address(address):
            await ctx.send("❌ Adresse invalide")
            return
            
        # Convertir en format checksum
        checksum_address = Web3.to_checksum_address(address)
        
        # Vérifier si l'adresse est déjà trackée
        if checksum_address in tracking_configs:
            await ctx.send("❌ Cette adresse est déjà trackée")
            return
            
        # Initialiser la configuration
        config = {
            'channel_id': ctx.channel.id  # Sauvegarder l'ID du canal
        }
        
        # Parser les arguments optionnels
        for arg in args:
            if arg.startswith('token='):
                token_address = arg.split('=')[1]
                if not w3.is_address(token_address):
                    await ctx.send(f"❌ Adresse de token invalide: {token_address}")
                    return
                config['token_address'] = Web3.to_checksum_address(token_address)
            elif arg.startswith('min='):
                try:
                    min_amount = float(arg.split('=')[1])
                    if min_amount <= 0:
                        raise ValueError("Le montant minimum doit être positif")
                    config['min_amount'] = min_amount
                except ValueError as e:
                    await ctx.send(f"❌ Montant minimum invalide: {str(e)}")
                    return
        
        # Ajouter l'adresse à la configuration
        tracking_configs[checksum_address] = config
        
        # Sauvegarder les configurations
        data_manager.save_data(tracking_configs)
        
        # Construire le message de confirmation
        filters = []
        if config.get('token_address'):
            filters.append(f"Token: {config['token_address']}")
        if config.get('min_amount'):
            filters.append(f"Min: {config['min_amount']} ETH")
            
        filter_text = " | ".join(filters) if filters else "Aucun filtre"
        await ctx.send(f"✅ Tracking activé pour {checksum_address}\nFiltres: {filter_text}")
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")
        logger.error(f"Erreur lors du tracking de l'adresse {address}: {str(e)}")

@bot.command(name='untrack')
async def untrack_address(ctx, address: str):
    """Retirer une adresse du tracking"""
    try:
        if not w3.is_address(address):
            await ctx.send("❌ Adresse invalide")
            return

        # Conversion en checksum address
        checksum_address = Web3.to_checksum_address(address)
        
        if checksum_address in tracking_configs:
            del tracking_configs[checksum_address]
            # Sauvegarder les configurations
            data_manager.save_data(tracking_configs)
            await ctx.send(f"✅ Adresse {checksum_address} retirée du tracking")
        else:
            await ctx.send("❌ Cette adresse n'est pas trackée")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='list')
async def list_addresses(ctx):
    """Lister les adresses trackées"""
    try:
        if not tracking_configs:
            await ctx.send("❌ Aucune adresse n'est trackée")
            return
            
        embed = discord.Embed(title="📋 Adresses trackées", color=0x00ff00)
        
        for address, config in tracking_configs.items():
            filters = []
            if config.get('token_address'):
                filters.append(f"Token: {config['token_address']}")
            if config.get('min_amount'):
                filters.append(f"Min: {config['min_amount']} ETH")
                
            filter_text = " | ".join(filters) if filters else "Aucun filtre"
            embed.add_field(
                name=f"🔍 {address}", 
                value=f"Filtres: {filter_text}", 
                inline=False
            )
            
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

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
            logger.error(f"Erreur bloc: {str(e)}")
            block_msg = "❌ Erreur lors de la récupération du bloc"
        
        # Test de récupération d'une transaction récente de manière simplifiée
        try:
            block = w3.eth.get_block('latest')
            if block and 'transactions' in block and block['transactions']:
                tx_hash = block['transactions'][0].hex() if isinstance(block['transactions'][0], (bytes, bytearray)) else str(block['transactions'][0])
                short_hash = f"{tx_hash[:10]}...{tx_hash[-8:]}"
                tx_msg = f"📝 Dernière transaction: `{short_hash}`"
            else:
                tx_msg = "❌ Aucune transaction dans le dernier bloc"
        except Exception as e:
            logger.error(f"Erreur transaction: {str(e)}")
            tx_msg = "❌ Erreur lors de la récupération des transactions"
            
        # Test de l'API Alchemy
        alchemy_api_key = os.getenv('ALCHEMY_API_KEY')
        if alchemy_api_key:
            try:
                alchemy_url = f"https://base-mainnet.g.alchemy.com/v2/{alchemy_api_key}"
                alchemy_w3 = Web3(Web3.HTTPProvider(alchemy_url))
                is_alchemy_connected = alchemy_w3.is_connected()
                alchemy_msg = f"🔌 Connexion Alchemy: {'✅' if is_alchemy_connected else '❌'}"
            except Exception as e:
                logger.error(f"Erreur Alchemy: {str(e)}")
                alchemy_msg = "❌ Erreur de connexion Alchemy"
        else:
            alchemy_msg = "⚠️ Pas de clé Alchemy configurée"
        
        # Envoyer le rapport
        status_report = f"""
**Test de Connexion Base**
{connection_msg}
{block_msg}
{tx_msg}
{alchemy_msg}

**Provider URL**: `{w3.provider.endpoint_uri}`
"""
        await ctx.send(status_report)
        
    except Exception as e:
        error_msg = f"❌ Erreur lors du test: {str(e)}"
        logger.error(error_msg)
        await ctx.send(error_msg)

@bot.command(name='alchemytest')
async def alchemy_test(ctx):
    """Teste explicitement la connexion à Alchemy et affiche le résultat"""
    try:
        # Configuration d'une connexion directe à Alchemy
        alchemy_url = "https://base-mainnet.g.alchemy.com/v2/0mT-QZ3Jim1d81aTEh93YkE3UK8bpmTc"
        w3_alchemy = Web3(Web3.HTTPProvider(
            alchemy_url,
            request_kwargs={
                'timeout': 30,
                'headers': {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
            }
        ))

        # Test de connexion basique
        is_connected = w3_alchemy.is_connected()
        if not is_connected:
            await ctx.send("❌ Impossible de se connecter à Alchemy")
            return

        # Récupération du bloc spécifique (comme dans l'exemple)
        block = w3_alchemy.eth.get_block(123456)
        
        # Formatage de la réponse
        response = f"""✅ **Test Alchemy réussi !**

🔍 **Bloc 123456** :
• Hash: `{block['hash'].hex()}`
• Parent Hash: `{block['parentHash'].hex()}`
• Timestamp: {block['timestamp']}
• Nombre de transactions: {len(block['transactions'])}

🌐 **URL**: `{alchemy_url}`"""
        
        await ctx.send(response)
        
    except Exception as e:
        error_msg = f"❌ Erreur lors du test Alchemy : {str(e)}"
        logger.error(error_msg)
        await ctx.send(error_msg)

async def process_transaction(tx_hash: str, address: str, is_outgoing: bool = True):
    """Traite une transaction et envoie une notification Discord"""
    try:
        # Récupération des détails de la transaction
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        if not tx or not receipt:
            logger.warning(f"Transaction {tx_hash} introuvable")
            return
            
        # Vérification du statut
        if receipt['status'] != 1:
            logger.info(f"Transaction {tx_hash} a échoué, pas de notification")
            return
            
        # Calcul de la valeur en ETH
        value_eth = w3.from_wei(tx['value'], 'ether')
        
        # Construction du message
        direction = "envoyé" if is_outgoing else "reçu"
        message = f"💸 Transaction {direction} pour {address}\n"
        message += f"**Montant:** {value_eth:.4f} ETH\n"
        message += f"**Hash:** `{tx_hash}`\n"
        message += f"**Block:** {receipt['blockNumber']}\n"
        
        if is_outgoing:
            message += f"**Destinataire:** `{tx['to']}`\n"
        else:
            message += f"**Expéditeur:** `{tx['from']}`\n"
            
        # Ajout du lien Basescan
        message += f"\n🔍 [Voir sur Basescan](https://basescan.org/tx/{tx_hash})"
        
        # Récupération du channel_id depuis la configuration
        if address in tracking_configs and 'channel_id' in tracking_configs[address]:
            channel_id = tracking_configs[address]['channel_id']
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(message)
                logger.info(f"Notification envoyée pour la transaction {tx_hash}")
            else:
                logger.error(f"Canal Discord {channel_id} introuvable pour l'adresse {address}")
        else:
            logger.error(f"Configuration de canal manquante pour l'adresse {address}")
            
    except Exception as e:
        logger.error(f"Erreur lors du traitement de la transaction {tx_hash}: {str(e)}")

# Lancer le bot
bot.run(os.getenv('DISCORD_TOKEN')) 