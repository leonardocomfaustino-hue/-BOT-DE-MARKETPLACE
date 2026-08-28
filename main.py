import os
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask
from threading import Thread

# =========================================================
# CONFIGURAÇÃO
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
PIX = os.getenv("PAYMENT_CPF", "067.663.641.14")

BASICA = "5,00"
PREMIUM = "15,00"

DB = "lojas.db"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# RENDER
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot online!"

def servidor_web():
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )

Thread(
    target=servidor_web,
    daemon=True
).start()

# =========================================================
# BANCO
# =========================================================

def banco():

    db = sqlite3.connect(DB)

    db.execute("""
        CREATE TABLE IF NOT EXISTS lojas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild INTEGER,
            dono INTEGER,
            categoria INTEGER,
            plano TEXT,
            vencimento TEXT,
            ativa INTEGER DEFAULT 1
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja INTEGER,
            canal INTEGER,
            nome TEXT,
            descricao TEXT,
            preco TEXT,
            estoque INTEGER,
            pagamento TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild INTEGER,
            usuario INTEGER,
            plano TEXT,
            valor TEXT,
            canal INTEGER,
            aprovado INTEGER DEFAULT 0
        )
    """)

    db.commit()

    return db


banco()

# =========================================================
# FUNÇÕES
# =========================================================

def pegar_loja(guild, dono):

    db = banco()

    loja = db.execute("""
        SELECT *
        FROM lojas
        WHERE guild=? AND dono=? AND ativa=1
        ORDER BY id DESC
        LIMIT 1
    """, (guild, dono)).fetchone()

    db.close()

    return loja


def pegar_produto(produto):

    db = banco()

    p = db.execute("""
        SELECT *
        FROM produtos
        WHERE id=?
    """, (produto,)).fetchone()

    db.close()

    return p


# =========================================================
# MODAL - CRIAR LOJA
# =========================================================

class CriarLoja(discord.ui.Modal, title="🏪 Criar Loja"):

    nome = discord.ui.TextInput(
        label="Nome do canal",
        placeholder="minha-loja",
        max_length=80
    )

    async def on_submit(self, interaction):

        guild = interaction.guild
        user = interaction.user

        nome = (
            self.nome.value
            .lower()
            .replace(" ", "-")
        )

        # Categoria
        categoria = await guild.create_category(
            f"🏪・LOJA・{user.display_name}"
        )

        # Esconder para todos
        await categoria.set_permissions(
            guild.default_role,
            view_channel=False
        )

        # Dono
        await categoria.set_permissions(
            user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        # Canal
        canal = await guild.create_text_channel(
            nome,
            category=categoria
        )

        # Vencimento
        vencimento = (
            datetime.now(timezone.utc)
            + timedelta(days=30)
        )

        db = banco()

        db.execute("""
            INSERT INTO lojas
            (guild,dono,categoria,plano,vencimento)
            VALUES(?,?,?,?,?)
        """, (
            guild.id,
            user.id,
            categoria.id,
            "basica",
            vencimento.isoformat()
        ))

        db.commit()

        loja_id = db.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        db.close()

        # Painel
        embed = discord.Embed(
            title=f"🏪 {nome}",
            description=(
                f"Olá {user.mention}!\n\n"
                "Esta é a sua loja.\n"
                "Use os botões abaixo para administrar."
            ),
            color=0x3498DB
        )

        embed.add_field(
            name="⏰ Vencimento",
            value=f"<t:{int(vencimento.timestamp())}:F>",
            inline=False
        )

        await canal.send(
            embed=embed,
            view=PainelLoja(loja_id, user.id)
        )

        await interaction.response.send_message(
            f"✅ Loja criada: {canal.mention}",
            ephemeral=True
        )


# =========================================================
# MODAL - PRODUTO
# =========================================================

class ProdutoModal(discord.ui.Modal, title="📦 Produto"):

    nome = discord.ui.TextInput(
        label="Nome",
        max_length=100
    )

    descricao = discord.ui.TextInput(
        label="Descrição",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    preco = discord.ui.TextInput(
        label="Preço",
        placeholder="R$5,00"
    )

    estoque = discord.ui.TextInput(
        label="Estoque",
        placeholder="10 ou ilimitado"
    )

    pagamento = discord.ui.TextInput(
        label="Pagamento",
        placeholder="Pix, CPF, Mercado Pago..."
    )

    def __init__(self, loja_id, dono):

        super().__init__()

        self.loja_id = loja_id
        self.dono = dono

    async def on_submit(self, interaction):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Você não é o dono dessa loja.",
                ephemeral=True
            )

        try:

            if self.estoque.value.lower() == "ilimitado":
                estoque = -1
            else:
                estoque = int(self.estoque.value)

                if estoque < 0:
                    raise ValueError

        except:

            return await interaction.response.send_message(
                "❌ Estoque inválido. Use um número ou `ilimitado`.",
                ephemeral=True
            )

        db = banco()

        db.execute("""
            INSERT INTO produtos
            (loja,canal,nome,descricao,preco,estoque,pagamento)
            VALUES(?,?,?,?,?,?,?)
        """, (
            self.loja_id,
            interaction.channel.id,
            self.nome.value,
            self.descricao.value,
            self.preco.value,
            estoque,
            self.pagamento.value
        ))

        db.commit()
        db.close()

        await enviar_produto(
            interaction.channel,
            self.nome.value,
            self.descricao.value,
            self.preco.value,
            estoque,
            self.pagamento.value
        )

        await interaction.response.send_message(
            "✅ Produto adicionado!",
            ephemeral=True
        )


# =========================================================
# MODAL - EDITAR
# =========================================================

class EditarProduto(discord.ui.Modal, title="✏️ Editar Produto"):

    id_produto = discord.ui.TextInput(
        label="ID do produto"
    )

    nome = discord.ui.TextInput(
        label="Novo nome",
        required=False
    )

    preco = discord.ui.TextInput(
        label="Novo preço",
        required=False
    )

    estoque = discord.ui.TextInput(
        label="Novo estoque",
        placeholder="10 ou ilimitado",
        required=False
    )

    pagamento = discord.ui.TextInput(
        label="Novo pagamento",
        required=False
    )

    def __init__(self, dono):

        super().__init__()

        self.dono = dono

    async def on_submit(self, interaction):

        try:
            pid = int(self.id_produto.value)
        except:

            return await interaction.response.send_message(
                "❌ ID inválido.",
                ephemeral=True
            )

        produto = pegar_produto(pid)

        if not produto:

            return await interaction.response.send_message(
                "❌ Produto não encontrado.",
                ephemeral=True
            )

        loja = pegar_loja(
            interaction.guild.id,
            self.dono
        )

        if not loja or produto[1] != loja[0]:

            return await interaction.response.send_message(
                "❌ Esse produto não pertence à sua loja.",
                ephemeral=True
            )

        nome = self.nome.value or produto[3]
        preco = self.preco.value or produto[5]
        pagamento = self.pagamento.value or produto[7]

        if self.estoque.value:

            if self.estoque.value.lower() == "ilimitado":
                estoque = -1

            else:

                try:
                    estoque = int(self.estoque.value)

                    if estoque < 0:
                        raise ValueError

                except:

                    return await interaction.response.send_message(
                        "❌ Estoque inválido.",
                        ephemeral=True
                    )

        else:

            estoque = produto[6]

        db = banco()

        db.execute("""
            UPDATE produtos

            SET nome=?,
                preco=?,
                estoque=?,
                pagamento=?

            WHERE id=?
        """, (
            nome,
            preco,
            estoque,
            pagamento,
            pid
        ))

        db.commit()
        db.close()

        await interaction.response.send_message(
            "✅ Produto atualizado!",
            ephemeral=True
        )


# =========================================================
# PRODUTO
# =========================================================

async def enviar_produto(
    canal,
    nome,
    descricao,
    preco,
    estoque,
    pagamento
):

    if estoque == -1:
        estoque_texto = "♾️ Ilimitado"
    else:
        estoque_texto = str(estoque)

    embed = discord.Embed(
        title=f"📦 {nome}",
        description=descricao or "Sem descrição.",
        color=0x2ECC71
    )

    embed.add_field(
        name="💰 Preço",
        value=preco,
        inline=True
    )

    embed.add_field(
        name="📦 Estoque",
        value=estoque_texto,
        inline=True
    )

    embed.add_field(
        name="💳 Pagamento",
        value=pagamento,
        inline=False
    )

    await canal.send(embed=embed)


# =========================================================
# CRIAR CANAL
# =========================================================

class CanalModal(discord.ui.Modal, title="➕ Criar Canal"):

    nome = discord.ui.TextInput(
        label="Nome do canal",
        max_length=80
    )

    def __init__(self, dono):

        super().__init__()

        self.dono = dono

    async def on_submit(self, interaction):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Apenas o dono.",
                ephemeral=True
            )

        loja = pegar_loja(
            interaction.guild.id,
            self.dono
        )

        if not loja:

            return await interaction.response.send_message(
                "❌ Loja não encontrada.",
                ephemeral=True
            )

        categoria = interaction.guild.get_channel(
            loja[3]
        )

        nome = (
            self.nome.value
            .lower()
            .replace(" ", "-")
        )

        canal = await interaction.guild.create_text_channel(
            nome,
            category=categoria
        )

        await canal.set_permissions(
            interaction.guild.default_role,
            view_channel=False
        )

        await canal.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        await interaction.response.send_message(
            f"✅ Canal criado: {canal.mention}",
            ephemeral=True
        )


# =========================================================
# RENOVAÇÃO
# =========================================================

class RenovarView(discord.ui.View):

    def __init__(self, dono):

        super().__init__(timeout=300)

        self.dono = dono

    @discord.ui.button(
        label="Renovar 30 dias",
        emoji="🔄",
        style=discord.ButtonStyle.green
    )
    async def renovar(self, interaction, button):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Apenas o dono.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"💳 Pague **R${BASICA}** para renovar.\n\n"
            f"🔑 Pix/CPF:\n`{PIX}`\n\n"
            "Depois envie o comprovante para a equipe.",
            ephemeral=True
        )


# =========================================================
# PAINEL DA LOJA
# =========================================================

class PainelLoja(discord.ui.View):

    def __init__(self, loja_id, dono):

        super().__init__(timeout=None)

        self.loja_id = loja_id
        self.dono = dono

    @discord.ui.button(
        label="Adicionar Produto",
        emoji="📦",
        style=discord.ButtonStyle.green
    )
    async def adicionar(self, interaction, button):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Apenas o dono.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            ProdutoModal(
                self.loja_id,
                self.dono
            )
        )

    @discord.ui.button(
        label="Editar Produto",
        emoji="✏️",
        style=discord.ButtonStyle.blurple
    )
    async def editar(self, interaction, button):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Apenas o dono.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            EditarProduto(self.dono)
        )

    @discord.ui.button(
        label="Criar Canal",
        emoji="➕",
        style=discord.ButtonStyle.blurple
    )
    async def canal(self, interaction, button):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Apenas o dono.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            CanalModal(self.dono)
        )

    @discord.ui.button(
        label="Renovar",
        emoji="🔄",
        style=discord.ButtonStyle.green
    )
    async def renovar(self, interaction, button):

        if interaction.user.id != self.dono:

            return await interaction.response.send_message(
                "❌ Apenas o dono.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"🔄 **Renovação por 30 dias**\n\n"
            f"💰 Valor: R${BASICA}\n"
            f"💳 Pix/CPF: `{PIX}`\n\n"
            "Após pagar, envie o comprovante para a equipe.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Informações",
        emoji="ℹ️",
        style=discord.ButtonStyle.gray
    )
    async def info(self, interaction, button):

        loja = pegar_loja(
            interaction.guild.id,
            self.dono
        )

        if not loja:

            return await interaction.response.send_message(
                "❌ Loja não encontrada.",
                ephemeral=True
            )

        data = datetime.fromisoformat(
            loja[5]
        )

        await interaction.response.send_message(
            f"🏪 **Sua loja**\n\n"
            f"💎 Plano: {loja[4]}\n"
            f"⏰ Vencimento: <t:{int(data.timestamp())}:F>\n"
            f"🆔 ID: `{loja[0]}`",
            ephemeral=True
        )


# =========================================================
# PAGAMENTO
# =========================================================

class AprovarView(discord.ui.View):

    def __init__(self, usuario, plano):

        super().__init__(timeout=None)

        self.usuario = usuario
        self.plano = plano

    @discord.ui.button(
        label="Aprovação",
        emoji="✅",
        style=discord.ButtonStyle.green
    )
    async def aprovar(self, interaction, button):

        if not interaction.user.guild_permissions.administrator:

            return await interaction.response.send_message(
                "❌ Apenas administradores.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            CriarLoja()
        )


# =========================================================
# PLANOS
# =========================================================

class Planos(discord.ui.View):

    @discord.ui.button(
        label="Básica — R$5",
        emoji="🥉",
        style=discord.ButtonStyle.green
    )
    async def basica(self, interaction, button):

        await pagamento(
            interaction,
            "Básica",
            BASICA
        )

    @discord.ui.button(
        label="Premium — R$15",
        emoji="👑",
        style=discord.ButtonStyle.blurple
    )
    async def premium(self, interaction, button):

        await pagamento(
            interaction,
            "Premium",
            PREMIUM
        )


async def pagamento(
    interaction,
    plano,
    valor
):

    guild = interaction.guild
    user = interaction.user

    canal = await guild.create_text_channel(
        f"⏳・pagamento-{user.name}"
    )

    await canal.set_permissions(
        guild.default_role,
        view_channel=False
    )

    await canal.set_permissions(
        user,
        view_channel=True,
        send_messages=True,
        read_message_history=True
    )

    db = banco()

    db.execute("""
        INSERT INTO pagamentos
        (guild,usuario,plano,valor,canal)
        VALUES(?,?,?,?,?)
    """, (
        guild.id,
        user.id,
        plano,
        valor,
        canal.id
    ))

    db.commit()
    db.close()

    embed = discord.Embed(
        title="💳 Pagamento",
        color=0xF1C40F
    )

    embed.description = (
        f"👤 Cliente: {user.mention}\n"
        f"📦 Plano: **{plano}**\n"
        f"💰 Valor: **R${valor}**\n\n"
        f"🔑 Pix/CPF:\n`{PIX}`\n\n"
        "Envie o comprovante aqui.\n"
        "Depois aguarde a aprovação da equipe."
    )

    await canal.send(
        embed=embed,
        view=AprovarView(
            user.id,
            plano
        )
    )

    await interaction.response.send_message(
        f"✅ Canal de pagamento criado: {canal.mention}",
        ephemeral=True
    )


# =========================================================
# /LOJA
# =========================================================

@bot.tree.command(name="loja", description="Escolha seu plano")
async def loja(i):
    e=discord.Embed(title="🏪 Marketplace",description="Escolha:",color=0x3498DB)
    e.add_field(name="Basica R$5",value="basica",inline=False)
    e.add_field(name="Premium R$15",value="premium",inline=False)
    await i.response.send_message(embed=e,view=Planos(),ephemeral=True)
