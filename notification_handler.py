import discord
from typing import Dict
from datetime import datetime

class NotificationHandler:
    def __init__(self, bot):
        self.bot = bot

    async def send_notification(self, channel_id: int, transaction_info: Dict):
        """Envoie une notification Discord pour une transaction"""
        print(f"Tentative d'envoi de notification dans le channel {channel_id}")
        print(f"Informations de la transaction: {transaction_info}")
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"❌ Channel {channel_id} non trouvé")
            return
        
        print(f"Channel trouvé: {channel.name}")
        embed = self._create_embed(transaction_info)
        print("Embed créé, envoi de la notification...")
        
        try:
            await channel.send(embed=embed)
            print("✅ Notification envoyée avec succès")
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi de la notification: {e}")

    def _create_embed(self, tx_info: Dict) -> discord.Embed:
        """Crée un embed Discord pour la notification"""
        print("Création de l'embed pour la notification")
        # Définir la couleur selon le type de transaction
        color_map = {
            'eth_transfer': 0x3498db,      # Bleu
            'token_transfer': 0x2ecc71,    # Vert
            'contract_interaction': 0xe67e22,  # Orange
            'contract_creation': 0x9b59b6   # Violet
        }
        
        color = color_map.get(tx_info['type'], 0x95a5a6)
        print(f"Couleur sélectionnée: {color}")
        
        embed = discord.Embed(
            title=self._get_title(tx_info),
            color=color,
            timestamp=datetime.fromtimestamp(tx_info['timestamp'])
        )
        print(f"Titre de l'embed: {self._get_title(tx_info)}")

        # Ajouter les informations de base
        embed.add_field(
            name="Type",
            value=self._format_type(tx_info['type']),
            inline=True
        )
        print(f"Type ajouté: {self._format_type(tx_info['type'])}")
        
        embed.add_field(
            name="Statut",
            value="✅ Succès" if tx_info['status'] == 'success' else "❌ Échec",
            inline=True
        )
        print(f"Statut ajouté: {tx_info['status']}")

        # Ajouter les informations spécifiques selon le type
        if tx_info['type'] == 'eth_transfer':
            embed.add_field(
                name="Montant",
                value=f"{tx_info['value']:.4f} ETH",
                inline=True
            )
            print(f"Montant ETH ajouté: {tx_info['value']:.4f}")
        elif tx_info['type'] == 'token_transfer':
            if 'token_symbol' in tx_info:
                embed.add_field(
                    name="Token",
                    value=f"{tx_info['token_symbol']}",
                    inline=True
                )
                print(f"Symbole du token ajouté: {tx_info['token_symbol']}")

        # Ajouter les liens
        embed.add_field(
            name="Transaction",
            value=f"[Voir sur Basescan](https://basescan.org/tx/{tx_info['hash']})",
            inline=False
        )
        print(f"Lien Basescan ajouté pour la transaction {tx_info['hash']}")

        # Ajouter les adresses
        embed.add_field(
            name="De",
            value=f"[{tx_info['from'][:6]}...{tx_info['from'][-4:]}](https://basescan.org/address/{tx_info['from']})",
            inline=True
        )
        print(f"Adresse source ajoutée: {tx_info['from']}")
        
        if tx_info['to']:
            embed.add_field(
                name="Vers",
                value=f"[{tx_info['to'][:6]}...{tx_info['to'][-4:]}](https://basescan.org/address/{tx_info['to']})",
                inline=True
            )
            print(f"Adresse destination ajoutée: {tx_info['to']}")

        print("Embed créé avec succès")
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