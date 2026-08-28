import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")
    try:
        await bot.tree.sync()
        print("Comandos sincronizados")
    except Exception as e:
        print(e)

@bot.tree.command(name="ping", description="Teste o bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! Bot online 24h ✅")

@bot.tree.command(name="loja", description="Abrir marketplace")
async def loja(interaction: discord.Interaction):
    await interaction.response.send_message("🛒 Marketplace funcionando! Bot grátis no Koyeb")

bot.run(os.getenv("DISCORD_TOKEN"))
