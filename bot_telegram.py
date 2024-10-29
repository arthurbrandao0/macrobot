import os
import openai
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv

print("bot em execução")
# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações das APIs
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
openai.api_key = os.getenv('OPENAI_API_KEY')

# Armazena o total de informações nutricionais por usuário
info_nutricional_usuarios = {}

# Estados para a conversa
ADICIONAR_ALIMENTO = range(1)

# Mensagem de ajuda
mensagem_ajuda = (
    "! Eu sou seu assistente de contagem de calorias e macronutrientes. 🥗\n"
    "Envie uma descrição do alimento e quantidade (ex: *'2 bananas'* ou *'2 pães e um copo de café com leite'*) ou grave um áudio.\n"
    "Para resetar suas informações diárias, digite `/reset`."
)

# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.message.from_user.first_name
    print(user_name)

    async def adicionar_ao_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        resposta = query.data.lower()

    # Continue a lógica existente

    await update.message.reply_text(f"Olá, *{user_name}* {mensagem_ajuda}", parse_mode='Markdown')

# Função para consultar o ChatGPT sobre macronutrientes de alimentos
async def consultar_chatgpt_nutrientes(alimento):
    try:
        prompt = (
            "Forneça apenas uma resposta numérica direta contendo os valores de proteínas, carboidratos e gorduras para o alimento informado, separados por espaços, sem qualquer outra explicação. "
            "Por exemplo: '3.5 12.0 1.2' (proteínas carboidratos gorduras)."
            "Se você não reconhecer o alimento, responda com a seguinte mensagem: "
            f"'{mensagem_ajuda}' Apenas forneça os valores de proteínas, carboidratos e gorduras para os alimentos conhecidos.\n\n"
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
            await update.message.reply_text(f"{alimento}\n\nProteínas: {nutrientes_response.split()[0]} g\nCarboidratos: {nutrientes_response.split()[1]} g\nGorduras: {nutrientes_response.split()[2]} g\n\nGostaria de adicionar este alimento ao total diário? (Gostaria de adicionar este alimento ao total diário?)", reply_markup=reply_markup)
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
            await update.message.reply_text("nao entendi nada kkkk, explica melhor")
            return ConversationHandler.END

        # await update.message.reply_text(f"{message}\n\nProteínas: {nutrientes_response.split()[0]} g\nCarboidratos: {nutrientes_response.split()[1]} g\nGorduras: {nutrientes_response.split()[2]} g\n\nGostaria de adicionar este alimento ao total diário? (Responda com 'sim' ou 'não')")
        # reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Sim', callback_data='sim'), InlineKeyboardButton('Não', callback_data='nao')]])
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Sim', callback_data='sim'), InlineKeyboardButton('Não', callback_data='nao')]])


        await update.message.reply_text(
            f"{message}\n\nProteínas: {nutrientes_response.split()[0]} g\nCarboidratos: {nutrientes_response.split()[1]} g\nGorduras: {nutrientes_response.split()[2]} g\n\nGostaria de adicionar este alimento ao total diário?",
            reply_markup=reply_markup
        )
                
        #
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
            proteinas, carboidratos, gorduras = map(float, nutrientes_response.split())

            if user_id not in info_nutricional_usuarios:
                info_nutricional_usuarios[user_id] = {"calorias": 0, "proteinas": 0, "carboidratos": 0, "gorduras": 0}

            # Atualiza as informações nutricionais do usuário
            info_nutricional_usuarios[user_id]["proteinas"] += proteinas
            info_nutricional_usuarios[user_id]["carboidratos"] += carboidratos
            info_nutricional_usuarios[user_id]["gorduras"] += gorduras

            await query.edit_message_text(
                f"✅ '{context.user_data['alimento']}' - Informação Nutricional adicionada ao total diário:\n"
                f"Proteínas: {proteinas:.2f} g\n"
                f"Carboidratos: {carboidratos:.2f} g\n"
                f"Gorduras: {gorduras:.2f} g\n\n"
                f"🔢 Total consumido hoje:\n"
                f"Proteínas: {info_nutricional_usuarios[user_id]['proteinas']:.2f} g\n"
                f"Carboidratos: {info_nutricional_usuarios[user_id]['carboidratos']:.2f} g\n"
                f"Gorduras: {info_nutricional_usuarios[user_id]['gorduras']:.2f} g"
            )
        except ValueError:
            await query.edit_message_text("Erro ao interpretar os nutrientes. Por favor, tente novamente.")
    else:
        await query.edit_message_text("Ok, o alimento não foi adicionado ao total diário.")

    return ConversationHandler.END

# Função para resetar informações nutricionais
async def reset_info_nutricional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    info_nutricional_usuarios[user_id] = {"calorias": 0, "proteinas": 0, "carboidratos": 0, "gorduras": 0}
    await update.message.reply_text("🔄 Suas informações nutricionais foram resetadas para zero. Comece novamente!")

def main():
    # Configuração do bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers para os comandos e mensagens
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, adicionar_info_nutricional),
                      MessageHandler(filters.VOICE, adicionar_info_nutricional)],
        states={
            # ADICIONAR_ALIMENTO: [MessageHandler(filters.Regex('^(Sim|Não)$'), adicionar_ao_total)],
            ADICIONAR_ALIMENTO: [CallbackQueryHandler(adicionar_ao_total)]
        },
        fallbacks=[CommandHandler("reset", reset_info_nutricional)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_info_nutricional))
    application.add_handler(conv_handler)

    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()
