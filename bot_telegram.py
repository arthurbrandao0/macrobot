import os
import openai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações das APIs
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
openai.api_key = os.getenv('OPENAI_API_KEY')

# Armazena o total de informações nutricionais por usuário
info_nutricional_usuarios = {}

# Mensagem de ajuda
mensagem_ajuda = (
    "Olá! Eu sou seu assistente de contagem de calorias e macronutrientes. 🥗\n"
    "Envie uma descrição do alimento e quantidade (ex: '2 bananas') ou grave um áudio.\n"
    "Para resetar suas informações diárias, digite `/reset`."
)

# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(mensagem_ajuda)

# Função para consultar o ChatGPT sobre macronutrientes de alimentos
async def consultar_chatgpt_nutrientes(alimento):
    try:
        prompt = (
            "Com base na informação enviada (texto, áudio ou imagem), forneça uma contagem precisa ou estimada de "
            "proteínas, carboidratos e gorduras. A cada solicitação, esses dados devem ser somados ao total diário "
            "do usuário e mostrados no consumo geral do dia.\n"
            "Se você não reconhecer o alimento, responda com a seguinte mensagem: "
            f"'{mensagem_ajuda}' Apenas forneça os valores de proteínas, carboidratos e gorduras para os alimentos conhecidos.\n\n"
            f"Nutrientes para: {alimento}"
        )

        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
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
async def adicionar_info_nutricional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            await update.message.reply_text(f"{alimento}: {nutrientes_response}")
        except Exception as e:
            print(f"Erro ao processar áudio: {e}")
            await update.message.reply_text("Erro ao processar o áudio.")

    else:
        # Processa mensagens de texto como antes
        message = update.message.text

        print(message)
        nutrientes_response = await consultar_chatgpt_nutrientes(message)

        if mensagem_ajuda in nutrientes_response:
            await update.message.reply_text(nutrientes_response)
            return

        try:
            # Interpreta a resposta do ChatGPT
            calorias, proteinas, carboidratos, gorduras = map(float, nutrientes_response.split())

            if user_id not in info_nutricional_usuarios:
                info_nutricional_usuarios[user_id] = {"calorias": 0, "proteinas": 0, "carboidratos": 0, "gorduras": 0}

            # Atualiza as informações nutricionais do usuário
            info_nutricional_usuarios[user_id]["calorias"] += calorias
            info_nutricional_usuarios[user_id]["proteinas"] += proteinas
            info_nutricional_usuarios[user_id]["carboidratos"] += carboidratos
            info_nutricional_usuarios[user_id]["gorduras"] += gorduras

            await update.message.reply_text(
                f"✅ '{message}' - Informação Nutricional:\n"
                f"Calorias: {calorias:.2f} kcal\n"
                f"Proteínas: {proteinas:.2f} g\n"
                f"Carboidratos: {carboidratos:.2f} g\n"
                f"Gorduras: {gorduras:.2f} g\n\n"
                f"🔢 Total consumido hoje:\n"
                f"Calorias: {info_nutricional_usuarios[user_id]['calorias']:.2f} kcal\n"
                f"Proteínas: {info_nutricional_usuarios[user_id]['proteinas']:.2f} g\n"
                f"Carboidratos: {info_nutricional_usuarios[user_id]['carboidratos']:.2f} g\n"
                f"Gorduras: {info_nutricional_usuarios[user_id]['gorduras']:.2f} g"
            )
        except ValueError:
            await update.message.reply_text(nutrientes_response)

# Função para resetar informações nutricionais
async def reset_info_nutricional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    info_nutricional_usuarios[user_id] = {"calorias": 0, "proteinas": 0, "carboidratos": 0, "gorduras": 0}
    await update.message.reply_text("🔄 Suas informações nutricionais foram resetadas para zero. Comece novamente!")

def main():
    # Configuração do bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers para os comandos e mensagens
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_info_nutricional))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, adicionar_info_nutricional))
    application.add_handler(MessageHandler(filters.VOICE, adicionar_info_nutricional))

    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()
