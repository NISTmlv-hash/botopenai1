import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --------- Токены ----------
BOT_TOKEN = "8734975345:AAE2HZEc5vwGA0hD8gNdmlcIx-LqzzmKLIs"
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# --------- Модели ----------
AVAILABLE_MODELS = {
    "Gemma 3 27B (free)": "google/gemma-3-27b-it:free",
    "Llama 3.3 70B (free)": "meta-llama/llama-3.3-70b-instruct:free",
    "Qwen 2.5 7B (free)": "qwen/qwen2.5-7b-instruct:free",
    "DeepSeek R1 (free)": "deepseek/deepseek-r1:free",
    "Mistral 7B (free)": "mistralai/mistral-7b-instruct:free",
}

# --------- Навыки ----------
SKILLS = {
    "default": {
        "name": "🤖 Обычный ассистент",
        "system": "Ты полезный и дружелюбный ассистент. Отвечай развёрнуто, но по делу."
    },
    "code": {
        "name": "💻 Эксперт по коду (Claude Code style)",
        "system": (
            "Ты эксперт-программист. Твоя задача — писать чистый, эффективный код с краткими пояснениями. "
            "Отвечай только по существу, показывай готовые решения. Не используй длинные вступления."
        )
    },
    "creative": {
        "name": "🎨 Креативный писатель",
        "system": "Ты творческий писатель. Придумывай оригинальные истории, стихи, сценарии. Пиши ярко и образно."
    },
    "translator": {
        "name": "🌐 Переводчик",
        "system": "Ты профессиональный переводчик. Переводи текст максимально точно, сохраняя стиль и смысл."
    },
    "math": {
        "name": "📐 Математик",
        "system": "Ты математик. Решай задачи пошагово, объясняй ход решения. Используй строгие формулы."
    }
}

# --------- Клавиатуры ----------
def get_continue_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Продолжить", callback_data="continue")]])

def get_model_keyboard():
    kb = [[InlineKeyboardButton(name, callback_data=f"model_{mid}")] for name, mid in AVAILABLE_MODELS.items()]
    return InlineKeyboardMarkup(kb)

def get_skill_keyboard():
    kb = [[InlineKeyboardButton(skill["name"], callback_data=f"skill_{sid}")] for sid, skill in SKILLS.items()]
    return InlineKeyboardMarkup(kb)

# --------- Обработчики ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Добро пожаловать в YuriGPT!\n\n"
        "Я помогу общаться с дешёвыми ИИ-моделями через OpenRouter.\n"
        "Выберите модель и навык — и начнём!",
        reply_markup=get_continue_keyboard()
    )

async def handle_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выберите модель:", reply_markup=get_model_keyboard())
    context.user_data["state"] = "choosing_model"

async def handle_model_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model_id = query.data.split("_", 1)[1]
    model_name = next((k for k, v in AVAILABLE_MODELS.items() if v == model_id), model_id)
    context.user_data["model_id"] = model_id
    context.user_data["model_name"] = model_name
    context.user_data["state"] = "choosing_skill"
    await query.edit_message_text(
        f"✅ Модель: {model_name}\nТеперь выберите навык:",
        reply_markup=get_skill_keyboard()
    )

async def handle_skill_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    skill_id = query.data.split("_", 1)[1]
    skill = SKILLS.get(skill_id, SKILLS["default"])
    context.user_data["skill_id"] = skill_id
    context.user_data["system_prompt"] = skill["system"]
    context.user_data["state"] = "chatting"
    context.user_data["history"] = []
    await query.edit_message_text(
        f"🎯 Модель: {context.user_data['model_name']}\n"
        f"🧠 Навык: {skill['name']}\n\n"
        "Диалог начат! Пишите ваше сообщение.\n"
        "/reset — сменить модель/навык\n"
        "/skill — изменить только навык\n"
        "/models — список моделей"
    )

async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_data = context.user_data
    if user_data.get("state") != "chatting":
        return

    history = user_data.get("history", [])
    system_prompt = user_data["system_prompt"]
    model_id = user_data["model_id"]

    if len(user_text) > 4000:
        await update.message.reply_text("Сообщение слишком длинное. Сократи до 4000 символов.")
        return

    history.append({"role": "user", "content": user_text})

    payload = {
        "model": model_id,
        "messages": [{"role": "system", "content": system_prompt}] + history[-20:]
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/YuriGPTBot",
        "X-Title": "YuriGPT"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(OPENROUTER_URL, json=payload, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    await update.message.reply_text(f"⚠️ Ошибка API: {resp.status}\n{error_text[:200]}")
                    return
                result = await resp.json()
        except asyncio.TimeoutError:
            await update.message.reply_text("⌛ Модель слишком долго отвечала. Попробуйте ещё раз.")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка сети: {e}")
            return

    try:
        assistant_message = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        await update.message.reply_text("🤕 Не удалось получить ответ от модели.")
        return

    history.append({"role": "assistant", "content": assistant_message})
    if len(history) > 40:
        history = history[-40:]
    user_data["history"] = history

    max_len = 4096
    for i in range(0, len(assistant_message), max_len):
        await update.message.reply_text(assistant_message[i:i+max_len])

# --------- Команды в диалоге ----------
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔄 Сброшено. Выберите модель заново.", reply_markup=get_model_keyboard())
    context.user_data["state"] = "choosing_model"

async def change_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите новый навык:", reply_markup=get_skill_keyboard())
    context.user_data["state"] = "choosing_skill"

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📋 Доступные модели:\n" + "\n".join(f"• {name}" for name in AVAILABLE_MODELS)
    await update.message.reply_text(text)

async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Кнопка уже не активна. Используйте /reset для новой сессии.", show_alert=True)

# --------- Запуск ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("skill", change_skill))
    app.add_handler(CommandHandler("models", list_models))

    app.add_handler(CallbackQueryHandler(handle_continue, pattern="^continue$"))
    app.add_handler(CallbackQueryHandler(handle_model_choice, pattern="^model_"))
    app.add_handler(CallbackQueryHandler(handle_skill_choice, pattern="^skill_"))
    app.add_handler(CallbackQueryHandler(unknown_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_message))

    print("YuriGPT запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()