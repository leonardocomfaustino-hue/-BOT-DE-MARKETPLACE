import os
import discord
from discord.ext import commands
from threading import Thread
from flask import Flask

# =========================================================
# CONFIGURACAO
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# No Render:
# PAYMENT_KEY = sua chave Pix ou CPF
PIX = os.getenv("PAYMENT_KEY", "CONFIGURE_PAYMENT_KEY")

# ID da categoria onde as lojas serao criadas
CATEGORIA_ID = 1543035058711953518

# SOMENTE ESTE ID PODE APROVAR
DONO_ID = 1503854197307871373

# Precos
PRECO_BASICA = "5,00"
PRECO_PREMIUM = "15,00"


# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# RENDER / FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot online!"


def iniciar_web():

    port = int(
        os.getenv("PORT", "10000")
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


Thread(
    target=iniciar_web,
    daemon=True
).start()


# =========================================================
# PAINEL DA LOJA
# =========================================================

class PainelLoja(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    # -----------------------------------------------------
    # PLANO BASICO
    # -----------------------------------------------------

    @discord.ui.button(
        label="Basica - R$5,00",
        style=discord.ButtonStyle.green,
        custom_id="comprar_basica"
    )
    async def basica(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await criar_pagamento(
            interaction,
            "Basica",
            PRECO_BASICA
        )

    # -----------------------------------------------------
    # PLANO PREMIUM
    # -----------------------------------------------------

    @discord.ui.button(
        label="Premium - R$15,00",
        style=discord.ButtonStyle.blurple,
        custom_id="comprar_premium"
    )
    async def premium(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await criar_pagamento(
            interaction,
            "Premium",
            PRECO_PREMIUM
        )


# =========================================================
# PAGAMENTO
# =========================================================

async def criar_pagamento(
    interaction: discord.Interaction,
    plano: str,
    valor: str
):

    guild = interaction.guild
    usuario = interaction.user

    if guild is None:

        return await interaction.response.send_message(
            "Esse comando so funciona em servidor.",
            ephemeral=True
        )

    # -----------------------------------------------------
    # NOME DO CANAL DE PAGAMENTO
    # -----------------------------------------------------

    nome_usuario = (
        usuario.name
        .lower()
        .replace(" ", "-")
    )

    nome_canal = (
        f"pagamento-{nome_usuario}"
    )

    canal = await guild.create_text_channel(
        nome_canal
    )

    # -----------------------------------------------------
    # PERMISSOES
    # -----------------------------------------------------

    # Ninguem ve
    await canal.set_permissions(
        guild.default_role,
        view_channel=False
    )

    # Cliente ve
    await canal.set_permissions(
        usuario,
        view_channel=True,
        send_messages=True,
        read_message_history=True
    )

    # Voce ve
    dono = guild.get_member(
        DONO_ID
    )

    if dono:

        await canal.set_permissions(
            dono,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    # -----------------------------------------------------
    # PAGAMENTO
    # -----------------------------------------------------

    embed = discord.Embed(
        title="Pagamento da Loja",
        description=(
            f"Cliente: {usuario.mention}\n\n"
            f"Plano: **{plano}**\n"
            f"Valor: **R${valor}**\n\n"
            f"Pix:\n"
            f"`{PIX}`\n\n"
            "Faca o pagamento e envie o comprovante "
            "neste canal.\n\n"
            "Depois aguarde a aprovacao."
        ),
        color=0xF1C40F
    )

    embed.set_footer(
        text="Pagamento manual"
    )

    await canal.send(
        embed=embed,
        view=AprovarPagamento(
            usuario.id,
            plano,
            valor
        )
    )

    await interaction.response.send_message(
        f"Canal de pagamento criado: {canal.mention}",
        ephemeral=True
    )


# =========================================================
# APROVACAO
# =========================================================

class AprovarPagamento(discord.ui.View):

    def __init__(
        self,
        usuario_id: int,
        plano: str,
        valor: str
    ):

        super().__init__(
            timeout=None
        )

        self.usuario_id = usuario_id
        self.plano = plano
        self.valor = valor

    @discord.ui.button(
        label="Aprovar pagamento",
        style=discord.ButtonStyle.green,
        custom_id="aprovar_pagamento"
    )
    async def aprovar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        # =================================================
        # SOMENTE VOCE PODE APROVAR
        # =================================================

        if interaction.user.id != DONO_ID:

            return await interaction.response.send_message(
                "Voce nao tem permissao para aprovar pagamentos.",
                ephemeral=True
            )

        guild = interaction.guild

        if guild is None:

            return await interaction.response.send_message(
                "Servidor nao encontrado.",
                ephemeral=True
            )

        # -------------------------------------------------
        # ENCONTRAR CLIENTE
        # -------------------------------------------------

        membro = guild.get_member(
            self.usuario_id
        )

        if membro is None:

            try:

                membro = await guild.fetch_member(
                    self.usuario_id
                )

            except:

                return await interaction.response.send_message(
                    "Nao consegui encontrar o cliente.",
                    ephemeral=True
                )

        # -------------------------------------------------
        # ENCONTRAR CATEGORIA
        # -------------------------------------------------

        categoria = guild.get_channel(
            CATEGORIA_ID
        )

        if categoria is None:

            return await interaction.response.send_message(
                f"A categoria {CATEGORIA_ID} nao foi encontrada.",
                ephemeral=True
            )

        # -------------------------------------------------
        # NOME DA LOJA
        # -------------------------------------------------

        nome_usuario = (
            membro.display_name
            .lower()
            .replace(" ", "-")
        )

        nome_canal = (
            f"loja-de-{nome_usuario}"
        )

        # -------------------------------------------------
        # VERIFICAR SE JA EXISTE
        # -------------------------------------------------

        for canal_existente in categoria.channels:

            if canal_existente.name == nome_canal:

                return await interaction.response.send_message(
                    f"Esse usuario ja possui uma loja: "
                    f"{canal_existente.mention}",
                    ephemeral=True
                )

        # -------------------------------------------------
        # CRIAR LOJA
        # -------------------------------------------------

        canal = await guild.create_text_channel(
            nome_canal,
            category=categoria
        )

        # Ninguem ve
        await canal.set_permissions(
            guild.default_role,
            view_channel=False
        )

        # Cliente ve
        await canal.set_permissions(
            membro,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        # Voce ve
        dono = guild.get_member(
            DONO_ID
        )

        if dono:

            await canal.set_permissions(
                dono,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        # -------------------------------------------------
        # MENSAGEM DA LOJA
        # -------------------------------------------------

        embed = discord.Embed(
            title="Sua Loja",
            description=(
                f"Olá, {membro.mention}!\n\n"
                "Seu pagamento foi aprovado.\n"
                "Sua loja foi criada com sucesso."
            ),
            color=0x3498DB
        )

        embed.add_field(
            name="Plano",
            value=self.plano,
            inline=True
        )

        embed.add_field(
            name="Valor",
            value=f"R${self.valor}",
            inline=True
        )

        embed.add_field(
            name="Dono",
            value=membro.mention,
            inline=False
        )

        await canal.send(
            embed=embed
        )

        # -------------------------------------------------
        # AVISO PARA VOCE
        # -------------------------------------------------

        await interaction.response.send_message(
            f"Pagamento aprovado.\n"
            f"Loja criada: {canal.mention}",
            ephemeral=True
        )

        # -------------------------------------------------
        # DESATIVAR BOTAO
        # -------------------------------------------------

        button.disabled = True

        try:

            await interaction.message.edit(
                view=self
            )

        except:
            pass

        # -------------------------------------------------
        # AVISAR CLIENTE NO PRIVADO
        # -------------------------------------------------

        try:

            await membro.send(
                f"Seu pagamento foi aprovado!\n\n"
                f"Sua loja foi criada no servidor "
                f"{guild.name}.\n"
                f"Canal: {canal.mention}"
            )

        except:
            pass


# =========================================================
# COMANDO /LOJA
# =========================================================

@bot.tree.command(
    name="loja",
    description="Abrir o painel de compra de lojas"
)
async def loja(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="Marketplace",
        description=(
            "Crie sua propria loja no servidor.\n\n"
            "Escolha um plano abaixo:"
        ),
        color=0x3498DB
    )

    embed.add_field(
        name="Loja Basica",
        value=(
            "Valor: **R$5,00**\n"
            "Loja basica"
        ),
        inline=False
    )

    embed.add_field(
        name="Loja Premium",
        value=(
            "Valor: **R$15,00**\n"
            "Loja premium"
        ),
        inline=False
    )

    embed.set_footer(
        text="Escolha um plano para continuar."
    )

    await interaction.response.send_message(
        embed=embed,
        view=PainelLoja(),
        ephemeral=True
    )


# =========================================================
# BOT ONLINE
# =========================================================

@bot.event
async def on_ready():

    print(
        f"Bot conectado como {bot.user}"
    )

    try:

        bot.add_view(
            PainelLoja()
        )

        await bot.tree.sync()

        print(
            "Comando /loja sincronizado."
        )

    except Exception as erro:

        print(
            f"Erro ao sincronizar comandos: {erro}"
        )


# =========================================================
# INICIAR
# =========================================================

if not TOKEN:

    print(
        "ERRO: DISCORD_TOKEN nao foi configurado."
    )

else:

    bot.run(TOKEN)
