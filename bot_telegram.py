import os
import openai
import sqlite3
import datetime
import pytz
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, JobQueue
from dotenv import load_dotenv

print("bot em execução")
# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações das APIs
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
openai.api_key = os.getenv('OPENAI_API_KEY')

# Conectar ao banco de dados SQLite
conn = sqlite3.connect('nutricao.db')
cursor = conn.cursor()

# Criação da tabela se ela não existir
cursor.execute('''
CREATE TABLE IF NOT EXISTS info_nutricional (
    user_id INTEGER,
    alimento TEXT,
    proteinas REAL,
    carboidratos REAL,
    gorduras REAL,
    calorias REAL,
    data_hora TEXT
)
''')
conn.commit()

# Função para enviar relatório diário para todos os usuários
async def enviar_relatorio_diario(context: ContextTypes.DEFAULT_TYPE):
    data_anterior = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    cursor.execute('SELECT DISTINCT user_id FROM info_nutricional')
    usuarios = cursor.fetchall()

    for usuario in usuarios:
        user_id = usuario[0]
        alimentos_consumidos, totais = consultar_totais_diarios(user_id, data_anterior)

        if alimentos_consumidos:
            mensagem_alimentos = "📊 Relatório do consumo de ontem:\n"
            for alimento in alimentos_consumidos:
                mensagem_alimentos += (
                    f"- {alimento[0]}: Proteínas: {alimento[1]:.2f} g, Carboidratos: {alimento[2]:.2f} g, Gorduras: {alimento[3]:.2f} g, Calorias: {alimento[4]:.2f} kcal\n"
                )
            await context.bot.send_message(chat_id=user_id, text=mensagem_alimentos)
        else:
            await context.bot.send_message(chat_id=user_id, text="Você não consumiu nenhum alimento ontem.")

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🔢 Total consumido ontem:\n"
                f"Proteínas: {totais['proteinas']:.2f} g\n"
                f"Carboidratos: {totais['carboidratos']:.2f} g\n"
                f"Gorduras: {totais['gorduras']:.2f} g\n"
                f"Calorias: {totais['calorias']:.2f} kcal"
            )
        )

# Função de comando para enviar o relatório manualmente
async def enviar_relatorio_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await enviar_relatorio_diario(context)

def main():
    # Configuração do bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Definir o fuso horário para UTC-3
    timezone_utc_3 = pytz.timezone("America/Sao_Paulo")

    # Agendar envio de relatório diário para todos os usuários às 8h da manhã no fuso horário UTC-3
    job_queue = application.job_queue
    job_queue.run_daily(
        enviar_relatorio_diario, 
        time=datetime.time(hour=8, minute=0, second=0, tzinfo=timezone_utc_3)
    )

    # Handlers para os comandos e mensagens
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, adicionar_info_nutricional),
                      MessageHandler(filters.VOICE, adicionar_info_nutricional)],
        states={
            ADICIONAR_ALIMENTO: [CallbackQueryHandler(adicionar_ao_total)]
        },
        fallbacks=[CommandHandler("reset", reset_info_nutricional)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_info_nutricional))
    application.add_handler(CommandHandler("totais", mostrar_totais_diarios))
    application.add_handler(CommandHandler("enviar_relatorio", enviar_relatorio_manual))
    application.add_handler(conv_handler)

    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()
