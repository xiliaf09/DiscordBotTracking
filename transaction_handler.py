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
            tx = self.w3.eth.get_transaction(tx_hash)
            tx_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            # Vérifier si la transaction correspond aux filtres
            if not self._matches_filters(tx, tx_receipt, config.get('filters', {})):
                return None

            # Analyser le type de transaction
            tx_type = self._determine_transaction_type(tx, tx_receipt)
            
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

            # Ajouter des informations spécifiques selon le type de transaction
            if tx_type == 'token_transfer':
                token_info = await self._get_token_info(tx['to'])
                notification.update(token_info)
            
            return notification

        except Exception as e:
            print(f"Erreur lors du traitement de la transaction {tx_hash}: {e}")
            return None

    def _matches_filters(self, tx: Dict, receipt: Dict, filters: Dict) -> bool:
        """Vérifie si la transaction correspond aux filtres configurés"""
        if not filters:
            return True

        # Vérifier les filtres de token
        if 'token_address' in filters:
            if tx['to'] and tx['to'].lower() != filters['token_address'].lower():
                return False

        # Vérifier les filtres de montant minimum
        if 'min_amount' in filters:
            if float(self.w3.from_wei(tx['value'], 'ether')) < float(filters['min_amount']):
                return False

        return True

    def _determine_transaction_type(self, tx: Dict, receipt: Dict) -> str:
        """Détermine le type de transaction"""
        if not tx['to']:
            return 'contract_creation'
        
        # Vérifier si c'est un transfert de token ERC20
        if tx['input'].startswith('0xa9059cbb'):
            return 'token_transfer'
        
        # Vérifier si c'est une interaction avec un contrat
        if receipt.get('contractAddress') or len(tx['input']) > 2:
            return 'contract_interaction'
        
        # Transfert simple d'ETH
        return 'eth_transfer'

    async def _get_token_info(self, token_address: str) -> Dict:
        """Récupère les informations d'un token ERC20"""
        try:
            contract = self.w3.eth.contract(
                address=to_checksum_address(token_address),
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