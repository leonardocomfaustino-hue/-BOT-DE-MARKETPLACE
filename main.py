import os
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import Thread

import discord
from discord.ext import commands, tasks
from flask import Flask


# =========================================================
# CONFIGURAÇÃO
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
PAYMENT_KEY = os.getenv("PAYMENT_KEY", "CONFIGURE_NO_RENDER")

PRECO_BASICA = "5,00"
PRECO_PREMIUM = "15,00"

DB_FILE = "lojas_v2.db"


# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# FLASK / RENDER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot online!"


def iniciar_web():
    port = int(os.getenv("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port
    )


Thread(
    target=iniciar_web,
    daemon=True
).start()


# =========================================================
# BANCO DE DADOS
# =========================================================

def conectar():

    con = sqlite3.connect(DB_FILE)

    con.execute("""
        CREATE TABLE IF NOT EXISTS lojas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            dono_id INTEGER NOT NULL,
            categoria_id INTEGER NOT NULL,
            plano TEXT NOT NULL,
            vencimento TEXT NOT NULL,
            ativa INTEGER DEFAULT 1
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_id INTEGER NOT NULL,
            canal_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            descricao TEXT,
            preco TEXT NOT NULL,
            estoque INTEGER NOT NULL,
            pagamento TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            plano TEXT NOT NULL,
            valor TEXT NOT NULL,
            canal_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            aprovado INTEGER DEFAULT 0
        )
    """)

    con.commit()

    return con


conectar().close()


# =========================================================
# FUNÇÕES DO BANCO
# =========================================================

def buscar_loja(guild_id, dono_id):

    con = conectar()

    loja = con.execute("""
        SELECT *
        FROM lojas
        WHERE guild_id = ?
        AND dono_id = ?
        AND ativa = 1
        ORDER BY id DESC
        LIMIT 1
    """, (
        guild_id,
        dono_id
    )).fetchone()

    con.close()

    return loja


def buscar_loja_por_categoria(categoria_id):

    if not categoria_id:
        return None

    con = conectar()

    loja = con.execute("""
        SELECT *
        FROM lojas
        WHERE categoria_id = ?
        AND ativa = 1
        LIMIT 1
    """, (
        categoria_id,
    )).fetchone()

    con.close()

    return loja


def buscar_produto(produto_id):

    con = conectar()

    produto = con.execute("""
        SELECT *
        FROM produtos
        WHERE id = ?
    """, (
        produto_id,
    )).fetchone()

    con.close()

    return produto


def buscar_pagamento_por_canal(canal_id):

    con = conectar()

    pagamento = con.execute("""
        SELECT *
        FROM pagamentos
        WHERE canal_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (
        canal_id,
    )).fetchone()

    con.close()

    return pagamento
# =========================================================
# VERIFICAR LOJAS EXPIRADAS
# =========================================================

async def verificar_lojas_expiradas():

    agora = datetime.now(timezone.utc)

    con = conectar()

    lojas = con.execute("""
        SELECT *
        FROM lojas
        WHERE ativa = 1
    """).fetchall()

    for loja in lojas:

        try:
            vencimento = datetime.fromisoformat(
                loja[5]
            )

        except Exception:
            continue

        if vencimento <= agora:

            con.execute("""
                UPDATE lojas
                SET ativa = 0
                WHERE id = ?
            """, (
                loja[0],
            ))

            guild = bot.get_guild(
                loja[1]
            )

            if guild:

                categoria = guild.get_channel(
                    loja[3]
                )

                if categoria:

                    try:

                        await categoria.set_permissions(
                            guild.default_role,
                            view_channel=False
                        )

                    except Exception:
                        pass

    con.commit()
    con.close()


@tasks.loop(minutes=10)
async def verificar_expiracoes():

    await verificar_lojas_expiradas()


# =========================================================
# EMBED DO PRODUTO
# =========================================================

async def enviar_produto(
    canal,
    produto_id,
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
        value=f"**R${preco}**",
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

    embed.set_footer(
        text=f"ID do produto: {produto_id}"
    )

    await canal.send(
        embed=embed
    )


# =========================================================
# MODAL - ADICIONAR PRODUTO
# =========================================================

class AdicionarProdutoModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="📦 Adicionar Produto"
        )

    nome = discord.ui.TextInput(
        label="Nome do produto",
        placeholder="Ex: Pack de Emotes",
        max_length=100
    )

    descricao = discord.ui.TextInput(
        label="Descrição",
        placeholder="Descrição do produto",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    preco = discord.ui.TextInput(
        label="Preço",
        placeholder="5,00",
        max_length=30
    )

    estoque = discord.ui.TextInput(
        label="Estoque",
        placeholder="10 ou ilimitado",
        max_length=30
    )

    pagamento = discord.ui.TextInput(
        label="Forma de pagamento",
        placeholder="Pix / Mercado Pago",
        max_length=100
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await interaction.response.send_message(
                "❌ Este comando só funciona em servidor.",
                ephemeral=True
            )

        loja = buscar_loja_por_categoria(
            interaction.channel.category_id
        )

        if not loja:

            return await interaction.response.send_message(
                "❌ Este canal não pertence a uma loja.",
                ephemeral=True
            )

        if interaction.user.id != loja[2]:

            return await interaction.response.send_message(
                "❌ Apenas o dono da loja pode adicionar produtos.",
                ephemeral=True
            )

        valor_estoque = self.estoque.value.strip()

        if valor_estoque.lower() == "ilimitado":

            estoque = -1

        else:

            try:

                estoque = int(
                    valor_estoque
                )

                if estoque < 0:
                    raise ValueError

            except ValueError:

                return await interaction.response.send_message(
                    "❌ Estoque inválido. Use um número ou `ilimitado`.",
                    ephemeral=True
                )

        con = conectar()

        cursor = con.execute("""
            INSERT INTO produtos (
                loja_id,
                canal_id,
                nome,
                descricao,
                preco,
                estoque,
                pagamento
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            loja[0],
            interaction.channel.id,
            self.nome.value.strip(),
            self.descricao.value.strip(),
            self.preco.value.strip(),
            estoque,
            self.pagamento.value.strip()
        ))

        produto_id = cursor.lastrowid

        con.commit()
        con.close()

        await enviar_produto(
            interaction.channel,
            produto_id,
            self.nome.value.strip(),
            self.descricao.value.strip(),
            self.preco.value.strip(),
            estoque,
            self.pagamento.value.strip()
        )

        await interaction.response.send_message(
            "✅ Produto adicionado com sucesso!",
            ephemeral=True
        )
# =========================================================
# MODAL - EDITAR PRODUTO
# =========================================================

class EditarProdutoModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="✏️ Editar Produto"
        )

    produto_id = discord.ui.TextInput(
        label="ID do produto",
        placeholder="Ex: 1",
        max_length=20
    )

    nome = discord.ui.TextInput(
        label="Novo nome",
        required=False,
        max_length=100
    )

    preco = discord.ui.TextInput(
        label="Novo preço",
        required=False,
        max_length=30
    )

    estoque = discord.ui.TextInput(
        label="Novo estoque",
        placeholder="10 ou ilimitado",
        required=False,
        max_length=30
    )

    pagamento = discord.ui.TextInput(
        label="Novo pagamento",
        required=False,
        max_length=100
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await interaction.response.send_message(
                "❌ Este comando só funciona em servidor.",
                ephemeral=True
            )

        try:

            pid = int(
                self.produto_id.value.strip()
            )

        except ValueError:

            return await interaction.response.send_message(
                "❌ ID inválido.",
                ephemeral=True
            )

        produto = buscar_produto(pid)

        if not produto:

            return await interaction.response.send_message(
                "❌ Produto não encontrado.",
                ephemeral=True
            )

        loja = buscar_loja(
            interaction.guild.id,
            interaction.user.id
        )

        if not loja or produto[1] != loja[0]:

            return await interaction.response.send_message(
                "❌ Esse produto não pertence à sua loja.",
                ephemeral=True
            )

        nome = (
            self.nome.value.strip()
            if self.nome.value.strip()
            else produto[3]
        )

        preco = (
            self.preco.value.strip()
            if self.preco.value.strip()
            else produto[5]
        )

        pagamento = (
            self.pagamento.value.strip()
            if self.pagamento.value.strip()
            else produto[7]
        )

        estoque_input = self.estoque.value.strip()

        if estoque_input:

            if estoque_input.lower() == "ilimitado":

                estoque = -1

            else:

                try:

                    estoque = int(
                        estoque_input
                    )

                    if estoque < 0:
                        raise ValueError

                except ValueError:

                    return await interaction.response.send_message(
                        "❌ Estoque inválido.",
                        ephemeral=True
                    )

        else:

            estoque = produto[6]

        con = conectar()

        con.execute("""
            UPDATE produtos
            SET nome = ?,
                preco = ?,
                estoque = ?,
                pagamento = ?
            WHERE id = ?
        """, (
            nome,
            preco,
            estoque,
            pagamento,
            pid
        ))

        con.commit()
        con.close()

        await interaction.response.send_message(
            "✅ Produto atualizado com sucesso!",
            ephemeral=True
        )


# =========================================================
# MODAL - EXCLUIR PRODUTO
# =========================================================

class ExcluirProdutoModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="🗑️ Excluir Produto"
        )

    produto_id = discord.ui.TextInput(
        label="ID do produto",
        placeholder="Ex: 1",
        max_length=20
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await interaction.response.send_message(
                "❌ Este comando só funciona em servidor.",
                ephemeral=True
            )

        try:

            pid = int(
                self.produto_id.value.strip()
            )

        except ValueError:

            return await interaction.response.send_message(
                "❌ ID inválido.",
                ephemeral=True
            )

        produto = buscar_produto(pid)

        if not produto:

            return await interaction.response.send_message(
                "❌ Produto não encontrado.",
                ephemeral=True
            )

        loja = buscar_loja(
            interaction.guild.id,
            interaction.user.id
        )

        if not loja or produto[1] != loja[0]:

            return await interaction.response.send_message(
                "❌ Esse produto não pertence à sua loja.",
                ephemeral=True
            )

        con = conectar()

        con.execute("""
            DELETE FROM produtos
            WHERE id = ?
        """, (
            pid,
        ))

        con.commit()
        con.close()

        await interaction.response.send_message(
            "🗑️ Produto excluído com sucesso!",
            ephemeral=True
        )


# =========================================================
# MODAL - CRIAR CANAL
# =========================================================

class CriarCanalModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="➕ Criar Canal"
        )

    nome = discord.ui.TextInput(
        label="Nome do canal",
        placeholder="ofertas",
        max_length=80
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await interaction.response.send_message(
                "❌ Este comando só funciona em servidor.",
                ephemeral=True
            )

        loja = buscar_loja(
            interaction.guild.id,
            interaction.user.id
        )

        if not loja:

            return await interaction.response.send_message(
                "❌ Você não possui uma loja ativa.",
                ephemeral=True
            )

        categoria = interaction.guild.get_channel(
            loja[3]
        )

        if not categoria:

            return await interaction.response.send_message(
                "❌ Categoria da loja não encontrada.",
                ephemeral=True
            )

        nome = (
            self.nome.value.strip()
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
            f"✅ Canal criado com sucesso: {canal.mention}",
            ephemeral=True
        )
# =========================================================
# MODAL - NOME DA LOJA
# =========================================================

class NomeLojaModal(discord.ui.Modal):

    def __init__(
        self,
        usuario_id,
        plano,
        pagamento_id
    ):

        super().__init__(
            title="🏪 Criar sua Loja"
        )

        self.usuario_id = usuario_id
        self.plano = plano
        self.pagamento_id = pagamento_id

    nome = discord.ui.TextInput(
        label="Nome do canal principal",
        placeholder="minha-loja",
        max_length=80
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await interaction.response.send_message(
                "❌ Este comando só funciona em servidor.",
                ephemeral=True
            )

        guild = interaction.guild

        membro = guild.get_member(
            self.usuario_id
        )

        if not membro:

            return await interaction.response.send_message(
                "❌ Usuário não encontrado.",
                ephemeral=True
            )

        loja_existente = buscar_loja(
            guild.id,
            self.usuario_id
        )

        if loja_existente:

            return await interaction.response.send_message(
                "❌ Este usuário já possui uma loja ativa.",
                ephemeral=True
            )

        nome = (
            self.nome.value.strip()
            .lower()
            .replace(" ", "-")
        )

        # =================================================
        # CATEGORIA DAS LOJAS
        # =================================================

        categoria = discord.utils.get(
            guild.categories,
            name="🏪・LOJAS"
        )

        if categoria is None:

            categoria = await guild.create_category(
                "🏪・LOJAS"
            )

        # Ninguém vê a categoria por padrão
        await categoria.set_permissions(
            guild.default_role,
            view_channel=False
        )

        # Dono da loja vê
        await categoria.set_permissions(
            membro,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        # =================================================
        # CANAL PRINCIPAL
        # =================================================

        canal = await guild.create_text_channel(
            nome,
            category=categoria
        )

        # =================================================
        # VENCIMENTO
        # =================================================

        vencimento = (
            datetime.now(timezone.utc)
            + timedelta(days=30)
        )

        # =================================================
        # SALVAR LOJA
        # =================================================

        con = conectar()

        cursor = con.execute("""
            INSER
