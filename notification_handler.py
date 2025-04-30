import discord
from typing import Dict
from datetime import datetime

class NotificationHandler:
    def __init__(self, bot):
        self.bot = bot

    async def send_notification(self, channel_id: int, transaction_info: Dict):
        """Envoie une notification Discord pour une transaction"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        embed = self._create_embed(transaction_info)
        await channel.send(embed=embed)

    def _create_embed(self, tx_info: Dict) -> discord.Embed:
        """Crée un embed Discord pour la notification"""
        # Définir la couleur selon le type de transaction
        color_map = {
            'eth_transfer': 0x3498db,      # Bleu
            'token_transfer': 0x2ecc71,    # Vert
            'contract_interaction': 0xe67e22,  # Orange
            'contract_creation': 0x9b59b6   # Violet
        }
        
        embed = discord.Embed(
            title=self._get_title(tx_info),
            color=color_map.get(tx_info['type'], 0x95a5a6),
            timestamp=datetime.fromtimestamp(tx_info['timestamp'])
        )

        # Ajouter les informations de base
        embed.add_field(
            name="Type",
            value=self._format_type(tx_info['type']),
            inline=True
        )
        
        embed.add_field(
            name="Statut",
            value="✅ Succès" if tx_info['status'] == 'success' else "❌ Échec",
            inline=True
        )

        # Ajouter les informations spécifiques selon le type
        if tx_info['type'] == 'eth_transfer':
            embed.add_field(
                name="Montant",
                value=f"{tx_info['value']:.4f} ETH",
                inline=True
            )
        elif tx_info['type'] == 'token_transfer':
            if 'token_symbol' in tx_info:
                embed.add_field(
                    name="Token",
                    value=f"{tx_info['token_symbol']}",
                    inline=True
                )

        # Ajouter les liens
        embed.add_field(
            name="Transaction",
            value=f"[Voir sur Basescan](https://basescan.org/tx/{tx_info['hash']})",
            inline=False
        )

        # Ajouter les adresses
        embed.add_field(
            name="De",
            value=f"[{tx_info['from'][:6]}...{tx_info['from'][-4:]}](https://basescan.org/address/{tx_info['from']})",
            inline=True
        )
        
        if tx_info['to']:
            embed.add_field(
                name="Vers",
                value=f"[{tx_info['to'][:6]}...{tx_info['to'][-4:]}](https://basescan.org/address/{tx_info['to']})",
                inline=True
            )

        return embed

    def _get_title(self, tx_info: Dict) -> str:
        """Génère le titre de la notification"""
        type_titles = {
            'eth_transfer': '💸 Transfert ETH',
            'token_transfer': '🪙 Transfert de Token',
            'contract_interaction': '📝 Interaction Contract',
            'contract_creation': '🏗️ Création de Contract'
        }
        return type_titles.get(tx_info['type'], '🔔 Nouvelle Transaction')

    def _format_type(self, tx_type: str) -> str:
        """Formate le type de transaction pour l'affichage"""
        type_formats = {
            'eth_transfer': 'Transfert ETH',
            'token_transfer': 'Transfert Token',
            'contract_interaction': 'Interaction Contract',
            'contract_creation': 'Création Contract'
        }
        return type_formats.get(tx_type, tx_type) 