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
import datetime

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
        self.processed_txs = set()  # Cache des transactions traitées
        self.address_to_name = {}  # Mapping adresse -> nom
        self.name_to_address = {}  # Mapping nom -> adresse
        self._init_mappings()

    def _init_mappings(self):
        """Initialise les mappings adresse<->nom depuis les données chargées"""
        for address, config in self.data.items():
            if 'name' in config:
                self.address_to_name[address] = config['name']
                self.name_to_address[config['name']] = address

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

    def save_data(self):
        """Sauvegarde les données dans le fichier JSON"""
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.data, f, indent=4)
            logger.info("Données sauvegardées avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des données: {str(e)}")

    def add_address(self, address: str, name: str, config: dict):
        """Ajoute une nouvelle adresse avec son nom"""
        config['name'] = name
        self.data[address] = config
        self.address_to_name[address] = name
        self.name_to_address[name] = address
        self.save_data()

    def remove_address(self, identifier: str) -> bool:
        """Supprime une adresse par son nom ou son adresse"""
        address = None
        name = None
        
        # Vérifier si l'identifiant est une adresse
        if Web3.is_address(identifier):
            address = Web3.to_checksum_address(identifier)
            name = self.address_to_name.get(address)
        else:
            # Sinon, considérer comme un nom
            name = identifier
            address = self.name_to_address.get(name)

        if address:
            if address in self.data:
                del self.data[address]
                if name:
                    del self.name_to_address[name]
                    del self.address_to_name[address]
                self.save_data()
                return True
        return False

    def get_name(self, address: str) -> str:
        """Récupère le nom associé à une adresse"""
        return self.address_to_name.get(address, address[:6] + '...' + address[-4:])

    def is_tx_processed(self, tx_hash: str) -> bool:
        """Vérifie si une transaction a déjà été traitée"""
        return tx_hash in self.processed_txs

    def mark_tx_processed(self, tx_hash: str):
        """Marque une transaction comme traitée"""
        self.processed_txs.add(tx_hash)

# ABI minimal pour détecter les transferts ERC20
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "name": "from",
                "type": "address"
            },
            {
                "indexed": True,
                "name": "to",
                "type": "address"
            },
            {
                "indexed": False,
                "name": "value",
                "type": "uint256"
            }
        ],
        "name": "Transfer",
        "type": "event"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

async def get_token_info(token_address: str) -> Dict:
    """Récupère les informations d'un token ERC20"""
    try:
        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        name = await token_contract.functions.name().call()
        symbol = await token_contract.functions.symbol().call()
        decimals = await token_contract.functions.decimals().call()
        return {
            "name": name,
            "symbol": symbol,
            "decimals": decimals
        }
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des infos du token {token_address}: {str(e)}")
        return None

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
    logger.info(f"Configurations chargées: {len(data_manager.data)} adresses")
    # Démarrer la tâche de monitoring
    bot.loop.create_task(monitor_addresses())

async def monitor_addresses():
    """Surveille les transactions pour les adresses trackées"""
    last_checked_block = {}
    
    while True:
        try:
            current_block = w3.eth.block_number
            logger.info(f"\n{'='*50}\nVérification du bloc {current_block}")
            
            for address in data_manager.data.keys():
                try:
                    # Conversion en checksum address
                    checksum_address = Web3.to_checksum_address(address)
                    
                    if address not in last_checked_block:
                        last_checked_block[address] = current_block - 1
                    
                    last_block = last_checked_block[address]
                    logger.info(f"\nVérification de l'adresse: {checksum_address}")
                    logger.info(f"Dernier bloc vérifié: {last_block}")
                    
                    # Vérification des transactions
                    block_range = range(last_block + 1, current_block + 1)
                    for block_num in block_range:
                        try:
                            block = w3.eth.get_block(block_num, True)
                            if block and 'transactions' in block:
                                for tx in block['transactions']:
                                    tx_hash = tx['hash'].hex()
                                    
                                    # Vérifier les transactions ETH
                                    if tx['from'].lower() == address.lower():
                                        await process_transaction(tx_hash, address, is_outgoing=True)
                                    elif tx['to'] and tx['to'].lower() == address.lower():
                                        await process_transaction(tx_hash, address, is_outgoing=False)
                                    
                                    # Vérifier les transferts ERC20
                                    try:
                                        receipt = w3.eth.get_transaction_receipt(tx_hash)
                                        if receipt and receipt['logs']:
                                            for log in receipt['logs']:
                                                # Vérifier si c'est un transfert ERC20 (Transfer event topic)
                                                if len(log['topics']) == 3 and log['topics'][0].hex() == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                                                    from_addr = '0x' + log['topics'][1].hex()[-40:]
                                                    to_addr = '0x' + log['topics'][2].hex()[-40:]
                                                    
                                                    # Vérifier les transferts ERC20 entrants
                                                    if to_addr.lower() == address.lower():
                                                        await process_token_transfer(tx_hash, address, log, is_outgoing=False)
                                                    # Vérifier les transferts ERC20 sortants
                                                    elif from_addr.lower() == address.lower():
                                                        await process_token_transfer(tx_hash, address, log, is_outgoing=True)
                                    except Exception as e:
                                        logger.error(f"Erreur lors de la vérification des transferts ERC20 pour {tx_hash}: {str(e)}")
                                        continue
                                        
                        except Exception as e:
                            logger.error(f"Erreur lors de la vérification du bloc {block_num}: {str(e)}")
                            continue
                    
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
async def track_address(ctx, address: str, name: str = None, *args):
    """Tracker une adresse avec un nom optionnel et des filtres"""
    try:
        # Valider l'adresse
        if not w3.is_address(address):
            await ctx.send("❌ Adresse invalide")
            return
            
        # Convertir en format checksum
        checksum_address = Web3.to_checksum_address(address)
        
        # Vérifier si l'adresse est déjà trackée
        if checksum_address in data_manager.data:
            await ctx.send("❌ Cette adresse est déjà trackée")
            return

        # Vérifier si le nom est déjà utilisé
        if name and name in data_manager.name_to_address:
            await ctx.send("❌ Ce nom est déjà utilisé")
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
        
        # Si aucun nom n'est fourni, utiliser une version courte de l'adresse
        if not name:
            name = f"{checksum_address[:6]}...{checksum_address[-4:]}"
        
        # Ajouter l'adresse avec son nom
        data_manager.add_address(checksum_address, name, config)
        
        # Construire le message de confirmation
        filters = []
        if config.get('token_address'):
            filters.append(f"Token: {config['token_address']}")
        if config.get('min_amount'):
            filters.append(f"Min: {config['min_amount']} ETH")
            
        filter_text = " | ".join(filters) if filters else "Aucun filtre"
        await ctx.send(f"✅ Tracking activé pour {name} ({checksum_address})\nFiltres: {filter_text}")
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")
        logger.error(f"Erreur lors du tracking de l'adresse {address}: {str(e)}")

@bot.command(name='untrack')
async def untrack_address(ctx, identifier: str):
    """Retirer une adresse du tracking par son nom ou son adresse"""
    try:
        if data_manager.remove_address(identifier):
            await ctx.send(f"✅ Adresse retirée du tracking")
        else:
            await ctx.send("❌ Cette adresse ou ce nom n'est pas tracké")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='list')
async def list_addresses(ctx):
    """Lister les adresses trackées"""
    try:
        if not data_manager.data:
            await ctx.send("❌ Aucune adresse n'est trackée")
            return
            
        embed = discord.Embed(title="📋 Adresses trackées", color=0x00ff00)
        
        for address, config in data_manager.data.items():
            name = config.get('name', address[:6] + '...' + address[-4:])
            filters = []
            if config.get('token_address'):
                filters.append(f"Token: {config['token_address']}")
            if config.get('min_amount'):
                filters.append(f"Min: {config['min_amount']} ETH")
                
            filter_text = " | ".join(filters) if filters else "Aucun filtre"
            embed.add_field(
                name=f"🔍 {name}",
                value=f"`{address}`\n{filter_text}",
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
        # Vérifier si la transaction a déjà été traitée
        if data_manager.is_tx_processed(tx_hash):
            return

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

        # Récupérer le nom de l'adresse
        address_name = data_manager.get_name(address)

        # Création de l'embed avec une barre verte sur le côté
        embed = discord.Embed(
            title=f"🔄 Nouvelle tx de {address_name}",
            color=0x00ff00,
            timestamp=datetime.datetime.utcnow()
        )

        # Type de transaction
        direction = "envoyée" if is_outgoing else "reçue"
        embed.add_field(
            name="Type",
            value=f"Transaction {direction} {'➡️' if is_outgoing else '⬅️'}",
            inline=False
        )

        # Montant ETH
        value_eth = w3.from_wei(tx['value'], 'ether')
        if value_eth > 0:
            embed.add_field(
                name="Montant ETH",
                value=f"{value_eth:.4f} ETH",
                inline=False
            )

        # Destinataire/Expéditeur
        if is_outgoing:
            embed.add_field(
                name="Destinataire",
                value=f"{tx['to']}",
                inline=False
            )
        else:
            embed.add_field(
                name="Expéditeur",
                value=f"{tx['from']}",
                inline=False
            )

        # Lien Basescan
        embed.add_field(
            name="🔍 Explorer",
            value=f"[Voir la transaction sur Basescan](https://basescan.org/tx/{tx_hash})",
            inline=False
        )

        # Timestamp en bas
        embed.set_footer(text=f"Aujourd'hui à {datetime.datetime.now().strftime('%H:%M')}")
        
        # Envoi de la notification
        if address in data_manager.data and 'channel_id' in data_manager.data[address]:
            channel_id = data_manager.data[address]['channel_id']
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)
                logger.info(f"Notification envoyée pour la transaction {tx_hash}")
                # Marquer la transaction comme traitée
                data_manager.mark_tx_processed(tx_hash)
            else:
                logger.error(f"Canal Discord {channel_id} introuvable pour l'adresse {address}")
        else:
            logger.error(f"Configuration de canal manquante pour l'adresse {address}")
            
    except Exception as e:
        logger.error(f"Erreur lors du traitement de la transaction {tx_hash}: {str(e)}")

async def process_token_transfer(tx_hash: str, address: str, log: dict, is_outgoing: bool = True):
    """Traite un transfert de token ERC20 et envoie une notification Discord"""
    try:
        # Récupérer les informations du token
        token_address = log['address']
        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        
        try:
            token_name = token_contract.functions.name().call()
            token_symbol = token_contract.functions.symbol().call()
            token_decimals = token_contract.functions.decimals().call()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos du token {token_address}: {str(e)}")
            token_name = "Unknown Token"
            token_symbol = "???"
            token_decimals = 18

        # Décoder le montant du transfert
        amount = int(log['data'], 16)
        token_amount = amount / (10 ** token_decimals)

        # Récupérer le nom de l'adresse trackée
        address_name = data_manager.get_name(address)

        # Création de l'embed
        embed = discord.Embed(
            title=f"🔄 Nouvelle tx de {address_name}",
            color=0x00ff00,
            timestamp=datetime.datetime.utcnow()
        )

        # Type de transaction
        direction = "envoyée" if is_outgoing else "reçue"
        embed.add_field(
            name="Type",
            value=f"Transaction {direction} {'➡️' if is_outgoing else '⬅️'}",
            inline=False
        )

        # Montant du token
        embed.add_field(
            name=f"Montant {token_symbol}",
            value=f"{token_amount:.4f} {token_symbol}",
            inline=False
        )

        # Destinataire/Expéditeur
        from_addr = '0x' + log['topics'][1].hex()[-40:]
        to_addr = '0x' + log['topics'][2].hex()[-40:]
        
        if is_outgoing:
            embed.add_field(
                name="Destinataire",
                value=f"{to_addr}",
                inline=False
            )
        else:
            embed.add_field(
                name="Expéditeur",
                value=f"{from_addr}",
                inline=False
            )

        # Lien Basescan
        embed.add_field(
            name="🔍 Explorer",
            value=f"[Voir la transaction sur Basescan](https://basescan.org/tx/{tx_hash})",
            inline=False
        )

        # Timestamp en bas
        embed.set_footer(text=f"Aujourd'hui à {datetime.datetime.now().strftime('%H:%M')}")
        
        # Envoi de la notification
        if address in data_manager.data and 'channel_id' in data_manager.data[address]:
            channel_id = data_manager.data[address]['channel_id']
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)
                logger.info(f"Notification envoyée pour le transfert de token {tx_hash}")
            else:
                logger.error(f"Canal Discord {channel_id} introuvable pour l'adresse {address}")
        else:
            logger.error(f"Configuration de canal manquante pour l'adresse {address}")
            
    except Exception as e:
        logger.error(f"Erreur lors du traitement du transfert de token {tx_hash}: {str(e)}")

# Lancer le bot
bot.run(os.getenv('DISCORD_TOKEN')) 