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
            print(f"\nTraitement détaillé de la transaction {tx_hash}")
            
            # Récupérer la transaction
            tx = self.w3.eth.get_transaction(tx_hash)
            if not tx:
                print(f"Transaction {tx_hash} non trouvée")
                return None
            
            # Récupérer le reçu de la transaction
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if not receipt:
                print(f"Reçu de transaction {tx_hash} non trouvé")
                return None
            
            # Vérifier si la transaction est réussie
            if not receipt['status']:
                print(f"Transaction {tx_hash} a échoué")
                return None
            
            # Vérifier les filtres
            if config.token_address:
                # Vérifier si c'est un transfert de token
                if not receipt.get('logs'):
                    print(f"Pas de logs pour la transaction {tx_hash}")
                    return None
                
                token_transfer = False
                for log in receipt['logs']:
                    if log['address'].lower() == config.token_address.lower():
                        token_transfer = True
                        break
                
                if not token_transfer:
                    print(f"Transaction {tx_hash} ne concerne pas le token {config.token_address}")
                    return None
            
            if config.min_amount:
                # Vérifier le montant minimum
                value_wei = int(tx['value'])
                if value_wei < config.min_amount:
                    print(f"Montant {value_wei} inférieur au minimum requis {config.min_amount}")
                    return None
            
            # Construire l'objet d'information
            tx_info = {
                'hash': tx_hash.hex(),
                'from': tx['from'],
                'to': tx['to'],
                'value': self.w3.from_wei(int(tx['value']), 'ether'),
                'block_number': receipt['blockNumber'],
                'timestamp': self.w3.eth.get_block(receipt['blockNumber'])['timestamp'],
                'gas_used': receipt['gasUsed'],
                'gas_price': self.w3.from_wei(int(tx['gasPrice']), 'gwei'),
                'status': 'success'
            }
            
            print(f"Transaction {tx_hash} traitée avec succès")
            return tx_info

        except Exception as e:
            print(f"Erreur lors du traitement de la transaction {tx_hash}: {str(e)}")
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