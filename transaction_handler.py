from web3 import Web3
from typing import Dict, Optional
import json
from eth_abi.codec import ABICodec
from eth_utils import to_checksum_address

class TransactionHandler:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.abi_codec = ABICodec(w3.codec)
        self.erc20_abi = json.loads('''[
            {"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},
            {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},
            {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"}
        ]''')

    async def process_transaction(self, tx_hash: str, config: Dict) -> Optional[Dict]:
        """Traite une transaction et retourne les informations pertinentes"""
        try:
            print(f"Traitement de la transaction {tx_hash}")
            tx = self.w3.eth.get_transaction(tx_hash)
            print(f"Transaction récupérée: {json.dumps(tx, indent=2)}")
            
            tx_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            print(f"Reçu de transaction: {json.dumps(tx_receipt, indent=2)}")
            
            # Vérifier si la transaction correspond aux filtres
            print(f"Vérification des filtres: {config.get('filters', {})}")
            if not self._matches_filters(tx, tx_receipt, config.get('filters', {})):
                print("Transaction ne correspond pas aux filtres")
                return None

            # Analyser le type de transaction
            tx_type = self._determine_transaction_type(tx, tx_receipt)
            print(f"Type de transaction détecté: {tx_type}")
            
            # Construire le message de notification
            notification = {
                'type': tx_type,
                'hash': tx_hash,
                'from': tx['from'],
                'to': tx['to'],
                'value': self.w3.from_wei(tx['value'], 'ether'),
                'block': tx_receipt['blockNumber'],
                'timestamp': self.w3.eth.get_block(tx_receipt['blockNumber'])['timestamp'],
                'gas_used': tx_receipt['gasUsed'],
                'status': 'success' if tx_receipt['status'] == 1 else 'failed'
            }
            print(f"Notification préparée: {json.dumps(notification, indent=2)}")

            # Ajouter des informations spécifiques selon le type de transaction
            if tx_type == 'token_transfer':
                print("Récupération des informations du token")
                token_info = await self._get_token_info(tx['to'])
                notification.update(token_info)
                print(f"Informations du token ajoutées: {json.dumps(token_info, indent=2)}")
            
            return notification

        except Exception as e:
            print(f"Erreur lors du traitement de la transaction {tx_hash}: {e}")
            return None

    def _matches_filters(self, tx: Dict, receipt: Dict, filters: Dict) -> bool:
        """Vérifie si la transaction correspond aux filtres configurés"""
        if not filters:
            print("Aucun filtre configuré, transaction acceptée")
            return True

        # Vérifier les filtres de token
        if 'token_address' in filters:
            print(f"Vérification du filtre token_address: {filters['token_address']}")
            if tx['to'] and tx['to'].lower() != filters['token_address'].lower():
                print(f"Adresse du token ne correspond pas: {tx['to']} != {filters['token_address']}")
                return False

        # Vérifier les filtres de montant minimum
        if 'min_amount' in filters:
            print(f"Vérification du filtre min_amount: {filters['min_amount']}")
            tx_value = float(self.w3.from_wei(tx['value'], 'ether'))
            if tx_value < float(filters['min_amount']):
                print(f"Montant insuffisant: {tx_value} < {filters['min_amount']}")
                return False

        print("Transaction correspond à tous les filtres")
        return True

    def _determine_transaction_type(self, tx: Dict, receipt: Dict) -> str:
        """Détermine le type de transaction"""
        print("Détermination du type de transaction")
        print(f"Input data: {tx['input']}")
        
        if not tx['to']:
            print("Transaction de création de contrat détectée")
            return 'contract_creation'
        
        # Vérifier si c'est un transfert de token ERC20
        if tx['input'].startswith('0xa9059cbb'):
            print("Transfert de token ERC20 détecté")
            return 'token_transfer'
        
        # Vérifier si c'est une interaction avec un contrat
        if receipt.get('contractAddress') or len(tx['input']) > 2:
            print("Interaction avec un contrat détectée")
            return 'contract_interaction'
        
        print("Transfert simple d'ETH détecté")
        return 'eth_transfer'

    async def _get_token_info(self, token_address: str) -> Dict:
        """Récupère les informations d'un token ERC20"""
        try:
            # S'assurer que l'adresse est au format checksum
            checksum_address = to_checksum_address(token_address)
            print(f"Récupération des informations du token à l'adresse {checksum_address}")
            
            contract = self.w3.eth.contract(
                address=checksum_address,
                abi=self.erc20_abi
            )
            
            return {
                'token_name': await contract.functions.name().call(),
                'token_symbol': await contract.functions.symbol().call(),
                'token_decimals': await contract.functions.decimals().call()
            }
        except Exception as e:
            print(f"Erreur lors de la récupération des informations du token: {e}")
            return {} 