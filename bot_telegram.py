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

# Definir o fuso horário (neste caso, UTC-3, representado por "America/Sao_Paulo")
timezone_utc_3 = pytz.timezone("America/Sao_Paulo")

# Obter o horário atual em UTC
utc_now = datetime.datetime.now(pytz.utc)

# Converter o horário atual para o fuso horário desejado (UTC-3)
local_time = utc_now.astimezone(timezone_utc_3)

# Imprimir a hora no fuso horário específico
print("Hora atual em UTC-3:", local_time.strftime("%Y-%m-%d %H:%M:%S"))

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

# Armazena o total de informações nutricionais por usuário
info_nutricional_usuarios = {}

# Estados para a conversa
ADICIONAR_ALIMENTO = range(1)

# Mensagem de ajuda
mensagem_ajuda = (
    "! Eu sou seu assistente de contagem de calorias e macronutrientes. 🥗\n"
    "Envie uma descrição do alimento e quantidade (ex: *'2 bananas'* ou *'2 pães e um copo de café com leite'*) ou grave um áudio.\n"
    "Para resetar suas informações diárias, digite `/reset`.\n"
    "Para ver o total de calorias, proteínas, carboidratos e gorduras consumidos hoje, digite `/totais`."
)

# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.message.from_user.first_name
    print(user_name)

    await update.message.reply_text(f"Olá, *{user_name}* {mensagem_ajuda}", parse_mode='Markdown')

# Função para consultar o ChatGPT sobre macronutrientes de alimentos
async def consultar_chatgpt_nutrientes(alimento):
    try:
        prompt = (
            "Forneça apenas uma resposta numérica direta contendo os valores de proteínas, carboidratos, gorduras e calorias para o alimento informado, separados por espaços, sem qualquer outra explicação. "
            "Por exemplo: '3.5 12.0 1.2 150' (proteínas carboidratos gorduras calorias)."
            "Se você não reconhecer o alimento, responda com a seguinte mensagem: "
            f"'{mensagem_ajuda}' Apenas forneça os valores de proteínas, carboidratos, gorduras e calorias para os alimentos conhecidos.\n\n"
            f"Nutrientes para: {alimento}"
        )

        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Erro ao consultar ChatGPT: {e}")
        return mensagem_ajuda

# Função para transcrever áudio com Whisper
async def transcrever_audio(audio_path):
    try:
        with open(audio_path, "rb") as audio_file:
            response = await openai.Audio.atranscribe("whisper-1", audio_file)
            return response['text']
    except Exception as e:
        print(f"Erro ao transcrever áudio: {e}")
        return "Erro ao transcrever áudio."

# Função para adicionar informações nutricionais dinamicamente
async def adicionar_info_nutricional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id

    if update.message.voice:
        try:
            # Baixa o áudio e transcreve para identificar o alimento
            voice_file = await update.message.voice.get_file()
            audio_path = f"{voice_file.file_id}.ogg"
            await voice_file.download_to_drive(audio_path)
            print("Áudio baixado para transcrição")

            # Transcreve o áudio para texto
            alimento = await transcrever_audio(audio_path)
            print(f"Áudio transcrito: {alimento}")

            nutrientes_response = await consultar_chatgpt_nutrientes(alimento)
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Sim', callback_data='sim'), InlineKeyboardButton('Não', callback_data='nao')]])
            await update.message.reply_text(f"{alimento}\n\nProteínas: {nutrientes_response.split()[0]} g\nCarboidratos: {nutrientes_response.split()[1]} g\nGorduras: {nutrientes_response.split()[2]} g\nCalorias: {nutrientes_response.split()[3]} kcal\n\nGostaria de adicionar este alimento ao total diário?", reply_markup=reply_markup)
            context.user_data['nutrientes_response'] = nutrientes_response
            context.user_data['alimento'] = alimento
            return ADICIONAR_ALIMENTO
        except Exception as e:
            print(f"Erro ao processar áudio: {e}")
            await update.message.reply_text("Erro ao processar o áudio.")

    else:
        # Processa mensagens de texto como antes
        message = update.message.text

        print(message)
        nutrientes_response = await consultar_chatgpt_nutrientes(message)

        if mensagem_ajuda in nutrientes_response:
            await update.message.reply_text("Não entendi nada, pode explicar melhor?")
            return ConversationHandler.END

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Sim', callback_data='sim'), InlineKeyboardButton('Não', callback_data='nao')]])

        await update.message.reply_text(
            f"{message}\n\nProteínas: {nutrientes_response.split()[0]} g\nCarboidratos: {nutrientes_response.split()[1]} g\nGorduras: {nutrientes_response.split()[2]} g\nCalorias: {nutrientes_response.split()[3]} kcal\n\nGostaria de adicionar este alimento ao total diário?",
            reply_markup=reply_markup
        )
        
        context.user_data['nutrientes_response'] = nutrientes_response
        context.user_data['alimento'] = message
        return ADICIONAR_ALIMENTO

# Função para processar a resposta do usuário sobre adicionar alimento
async def adicionar_ao_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    resposta = query.data.lower()

    if resposta == 'sim':
        try:
            nutrientes_response = context.user_data['nutrientes_response']
            proteinas, carboidratos, gorduras, calorias = map(float, nutrientes_response.split())

            # Salvar os dados no banco de dados com as calorias e a data/hora
            salvar_info_nutricional(user_id, context.user_data['alimento'], proteinas, carboidratos, gorduras, calorias)

            await query.edit_message_text(
                f"✅ '{context.user_data['alimento']}' - Informação Nutricional adicionada ao total diário:\n"
                f"Proteínas: {proteinas:.2f} g\n"
                f"Carboidratos: {carboidratos:.2f} g\n"
                f"Gorduras: {gorduras:.2f} g\n"
                f"Calorias: {calorias:.2f} kcal"
            )
        except ValueError:
            await query.edit_message_text("Erro ao interpretar os nutrientes. Por favor, tente novamente.")
    else:
        await query.edit_message_text("Ok, o alimento não foi adicionado ao total diário.")

    return ConversationHandler.END

# Função para resetar informações nutricionais
async def reset_info_nutricional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    cursor.execute('DELETE FROM info_nutricional WHERE user_id = ?', (user_id,))
    conn.commit()
    await update.message.reply_text("🔄 Suas informações nutricionais foram resetadas para zero. Comece novamente!")

# Função para consultar o total diário do usuário
def consultar_totais_diarios(user_id, data_consulta):
    # Consulta SQL para obter todos os alimentos consumidos na data fornecida
    cursor.execute('''
    SELECT alimento, proteinas, carboidratos, gorduras, calorias, data_hora
    FROM info_nutricional
    WHERE user_id = ? AND DATE(data_hora) = ?
    ''', (user_id, data_consulta))
    alimentos_consumidos = cursor.fetchall()

    # Consulta SQL para somar os nutrientes consumidos na data fornecida
    cursor.execute('''
    SELECT SUM(proteinas), SUM(carboidratos), SUM(gorduras), SUM(calorias)
    FROM info_nutricional
    WHERE user_id = ? AND DATE(data_hora) = ?
    ''', (user_id, data_consulta))
    resultado = cursor.fetchone()
    
    # Se houver algum resultado, retorna os valores, caso contrário, retorna 0 para cada nutriente
    totais = {
        "proteinas": resultado[0] or 0,
        "carboidratos": resultado[1] or 0,
        "gorduras": resultado[2] or 0,
        "calorias": resultado[3] or 0
    }
    
    return alimentos_consumidos, totais

# Função para salvar informações nutricionais no banco de dados
def salvar_info_nutricional(user_id, alimento, proteinas, carboidratos, gorduras, calorias):
    data_hora_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
    INSERT INTO info_nutricional (user_id, alimento, proteinas, carboidratos, gorduras, calorias, data_hora)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, alimento, proteinas, carboidratos, gorduras, calorias, data_hora_atual))
    conn.commit()

# Função para mostrar totais diários ao usuário
async def mostrar_totais_diarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    data_atual = datetime.datetime.now().strftime("%Y-%m-%d")
    alimentos_consumidos, totais = consultar_totais_diarios(user_id, data_atual)

    if alimentos_consumidos:
        mensagem_alimentos = "🍽️ Alimentos consumidos hoje:\n\n"
        for alimento in alimentos_consumidos:
            mensagem_alimentos += (
                f"*- {alimento[0]}*:\n\nProteínas: {alimento[1]:.2f} g,\nCarboidratos: {alimento[2]:.2f} g,\nGorduras: {alimento[3]:.2f} g,\nCalorias: {alimento[4]:.2f} kcal\n"
            )
        await update.message.reply_text(mensagem_alimentos, parse_mode='Markdown')
    else:
        await update.message.reply_text("Você ainda não consumiu nenhum alimento hoje.")

    await update.message.reply_text(
        f"🔢 Total consumido hoje:\n"
        f"*Proteínas*: {totais['proteinas']:.2f} g\n"
        f"*Carboidratos*: {totais['carboidratos']:.2f} g\n"
        f"*Gorduras*: {totais['gorduras']:.2f} g\n\n"
        f"*Calorias*: {totais['calorias']:.2f} kcal"
        , parse_mode='Markdown'
    )

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

    # Agendar envio de relatório diário para todos os usuários às 8h da manhã
    job_queue = application.job_queue
    job_queue.run_daily(enviar_relatorio_diario, time=datetime.time(hour=8, minute=0, second=0, tzinfo=timezone_utc_3))

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
