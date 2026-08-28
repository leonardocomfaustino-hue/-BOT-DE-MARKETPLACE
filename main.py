import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from flask import Flask
import threading

# --- TRUQUE RENDER GRATIS ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot Online! Loja funcionando"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

threading.Thread(target=run_web).start()
# --- FIM TRUQUE ---

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Sincronizado {len(synced)} comandos")
    except Exception as e:
        print(e)
    async with aiosqlite.connect("loja.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS compras (user_id INTEGER, plano TEXT)")
        await db.commit()

@bot.tree.command(name="loja", description="Veja os planos da nossa loja")
async def loja(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 Nossa Loja", description="Escolha seu plano abaixo:", color=0x00ff00)
    embed.add_field(name="📦 Basica - R$5/mes", value="Acesso basico", inline=False)
    embed.add_field(name="💎 Premium - R$15 vitalicio", value="Acesso total + destaque", inline=False)
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Comprar Basica R$5", style=discord.ButtonStyle.green, custom_id="basica"))
    view.add_item(discord.ui.Button(label="Comprar Premium R$15", style=discord.ButtonStyle.blurple, custom_id="premium"))
    await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_interaction(interaction):
    if interaction.type == discord.InteractionType.component:
        plano = interaction.data["custom_id"]
        async with aiosqlite.connect("loja.db") as db:
            await db.execute("INSERT INTO compras VALUES (?, ?)", (interaction.user.id, plano))
            await db.commit()
        await interaction.response.send_message(f"✅ Voce escolheu {plano}! Chame um admin.", ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
