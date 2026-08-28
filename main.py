import discord
from discord.ext import commands, tasks
import os
import datetime
import aiosqlite

# ===== SEU MARKETPLACE =====
PIX_CHAVE = "067.663.641.14"
DB = "marketplace.db"

PLANOS = {
    "basico": {"nome": "🥉 BÁSICA", "preco": "R$5,00/mês", "valor": 5.00, "tipo": "mensal"},
    "premium": {"nome": "👑 PREMIUM PERMANENTE", "preco": "R$15,00 ÚNICO", "valor": 15.00, "tipo": "vitalicio"}
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS lojas (
            user_id INTEGER PRIMARY KEY,
            nome TEXT, guild_id INTEGER, categoria_id INTEGER,
            cargo_id INTEGER, plano TEXT, status TEXT,
            inicio TEXT, vencimento TEXT
        )""")
        await db.commit()

@bot.event
async def on_ready():
    await init_db()
    await bot.tree.sync()
    print(f"Bot online: {bot.user}")
    verificar_expiradas.start()

@tasks.loop(hours=6)
async def verificar_expiradas():
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM lojas") as cur:
            lojas = await cur.fetchall()
    for loja in lojas:
        user_id, nome, guild_id, cat_id, cargo_id, plano, status, inicio, venc = loja
        if plano == "premium": # PERMANENTE NUNCA EXPIRA
            continue
        try:
            data_venc = datetime.datetime.strptime(venc, "%d/%m/%Y")
            if datetime.datetime.now() > data_venc and status == "ativa":
                guild = bot.get_guild(guild_id)
                if not guild: continue
                categoria = guild.get_channel(cat_id)
                if categoria:
                    await categoria.edit(name=f"🔒・EXPIRADA・{nome}")
                    member = guild.get_member(user_id)
                    if member:
                        await categoria.set_permissions(member, view_channel=False, send_messages=False)
                async with aiosqlite.connect(DB) as db:
                    await db.execute("UPDATE lojas SET status='expirada' WHERE user_id=?", (user_id,))
                    await db.commit()
                member = guild.get_member(user_id) if guild else None
                if member:
                    try: await member.send(f"🔒 Sua loja **{nome}** expirou! Use /loja para renovar. PIX: {PIX_CHAVE}")
                    except: pass
        except: pass

@bot.tree.command(name="ping", description="Teste o bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! ✅")

@bot.tree.command(name="loja", description="Criar sua loja no marketplace")
async def loja_cmd(interaction: discord.Interaction):
    view = discord.ui.View(timeout=None)
    b1 = discord.ui.Button(label="🥉 BÁSICA - R$5/mês", style=discord.ButtonStyle.secondary, custom_id="plano_basico")
    b2 = discord.ui.Button(label="👑 PREMIUM - R$15 Vitalício", style=discord.ButtonStyle.success, custom_id="plano_premium")
    view.add_item(b1)
    view.add_item(b2)

    embed = discord.Embed(title="🏪 MARKETPLACE - Escolha seu plano", color=0x2b2d31)
    embed.add_field(name="🥉 BÁSICA - R$5/mês", value="• 1 loja\n• 4 canais\n• Cargo 🏪・Dono da Loja\n• 5 produtos\n• Renova todo mês", inline=True)
    embed.add_field(name="👑 PREMIUM - R$15 ÚNICO", value="• Tudo da Básica\n• 6 canais\n• 100 produtos\n• Canal de divulgação\n• **PAGA 1 VEZ SÓ**\n• Nunca expira", inline=True)
    embed.set_footer(text="Liberação só após pagamento confirmado")
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type!= discord.InteractionType.component:
        return
    if not interaction.data.get('custom_id','').startswith("plano_"):
        return

    plano_key = interaction.data['custom_id'].replace("plano_", "")
    plano = PLANOS[plano_key]

    class NomeModal(discord.ui.Modal, title=f"Criar Loja {plano['nome']}"):
        nome_loja = discord.ui.TextInput(label="Nome da sua loja", placeholder="Ex: Loja do João", max_length=30)

        async def on_submit(self, modal_inter: discord.Interaction):
            await modal_inter.response.defer(ephemeral=True)

            async with aiosqlite.connect(DB) as db:
                async with db.execute("SELECT * FROM lojas WHERE user_id=?", (modal_inter.user.id,)) as cur:
                    if await cur.fetchone():
                        return await modal_inter.followup.send("❌ Você já tem loja! Use /minhaloja", ephemeral=True)

            # Cargo SEM ADM - só dono da loja dele
            cargo = await modal_inter.guild.create_role(
                name=f"🏪・Dono da Loja - {self.nome_loja.value}",
                permissions=discord.Permissions.none(),
                color=discord.Color.gold()
            )
            await modal_inter.user.add_roles(cargo)

            overwrites = {
                modal_inter.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                cargo: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True, attach_files=True),
                modal_inter.guild.me: discord.PermissionOverwrite(view_channel=True)
            }
            categoria = await modal_inter.guild.create_category(f"🏪・{self.nome_loja.value}", overwrites=overwrites)
            await modal_inter.guild.create_text_channel("📢│informacoes", category=categoria)
            await modal_inter.guild.create_text_channel("🛒│produtos", category=categoria)
            await modal_inter.guild.create_text_channel("⭐│feedbacks", category=categoria)
            await modal_inter.guild.create_text_channel("🎫│suporte", category=categoria)
            if plano_key == "premium":
                await modal_inter.guild.create_text_channel("📢│divulgacao", category=categoria)
                await modal_inter.guild.create_text_channel("💎│vip-exclusivo", category=categoria)

            inicio = datetime.datetime.now().strftime("%d/%m/%Y")
            if plano_key == "premium":
                venc = "VITALÍCIO"
            else:
                venc = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%d/%m/%Y")

            async with aiosqlite.connect(DB) as db:
                await db.execute("INSERT INTO lojas VALUES (?,?,?,?,?,?,?,?,?)",
                (modal_inter.user.id, self.nome_loja.value, modal_inter.guild.id, categoria.id, cargo.id, plano_key, "pendente", inicio, venc))
                await db.commit()

            embed_pix = discord.Embed(
                title="💳 PAGAMENTO PENDENTE - Aguardando confirmação",
                description=f"**Loja:** {self.nome_loja.value}\n**Plano:** {plano['nome']}\n**Valor:** {plano['preco']}\n\n**PIX (CPF):** `{PIX_CHAVE}`\n\n👉 Faça o PIX\n👉 Envie o comprovante no canal 🎫│suporte\n👉 Aguarde um ADM aprovar\n\n⚠️ Sua loja só libera após /aprovar",
                color=0xff0000
            )
            await modal_inter.followup.send(embed=embed_pix, ephemeral=True)

    await interaction.response.send_modal(NomeModal())

@bot.tree.command(name="aprovar", description="[ADMIN] Aprovar pagamento da loja")
async def aprovar(interaction: discord.Interaction, usuario: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Só ADM", ephemeral=True)

    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM lojas WHERE user_id=?", (usuario.id,)) as cur:
            loja = await cur.fetchone()
    if not loja:
        return await interaction.response.send_message("❌ Loja não encontrada", ephemeral=True)

    guild = interaction.guild
    categoria = guild.get_channel(loja[3])
    cargo = guild.get_role(loja[4])

    if categoria:
        await categoria.set_permissions(guild.default_role, view_channel=False)
        if cargo:
            await categoria.set_permissions(cargo, view_channel=True, send_messages=True, manage_messages=True, attach_files=True)
        await categoria.edit(name=f"🏪・{loja[1]}")

    if loja[5] == "premium":
        venc = "VITALÍCIO"
    else:
        venc = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%d/%m/%Y")

    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE lojas SET status='ativa', vencimento=? WHERE user_id=?", (venc, usuario.id))
        await db.commit()

    await interaction.response.send_message(f"✅ Loja **{loja[1]}** de {usuario.mention} liberada! Venc: {venc}")
    try:
        if loja[5] == "premium":
            await usuario.send(f"✅ Seu pagamento PREMIUM foi confirmado! Sua loja **{loja[1]}** agora é PERMANENTE e nunca expira! 👑")
        else:
            await usuario.send(f"✅ Pagamento confirmado! Sua loja **{loja[1]}** liberada até {venc}")
    except: pass

@bot.tree.command(name="minhaloja", description="Ver sua loja")
async def minhaloja(interaction: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM lojas WHERE user_id=?", (interaction.user.id,)) as cur:
            loja = await cur.fetchone()
    if not loja:
        return await interaction.response.send_message("Você não tem loja. Use /loja", ephemeral=True)

    embed = discord.Embed(title=f"🏪 {loja[1]}", color=0x00ff00 if loja[6]=="ativa" else 0xff0000)
    embed.add_field(name="Plano", value=PLANOS[loja[5]]['nome'], inline=True)
    embed.add_field(name="Preço", value=PLANOS[loja[5]]['preco'], inline=True)
    embed.add_field(name="Status", value=loja[6].upper(), inline=True)
    embed.add_field(name="Vencimento", value=loja[8], inline=True)
    embed.set_footer(text=f"Cargo: 🏪・Dono da Loja - {loja[1]} (sem ADM no servidor)")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="lojas", description="[ADMIN] Ver todas as lojas")
async def lojas_admin(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Só ADM", ephemeral=True)
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM lojas") as cur:
            todas = await cur.fetchall()
    if not todas:
        return await interaction.response.send_message("Nenhuma loja ainda", ephemeral=True)
    texto = ""
    for l in todas:
        texto += f"**{l[1]}** - <@{l[0]}> - {l[5]} - {l[6]} - {l[8]}\n"
    embed = discord.Embed(title="📊 Todas as Lojas", description=texto, color=0x2b2d31)
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
