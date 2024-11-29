import logging
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from telegram.error import NetworkError, TimedOut
from dotenv import load_dotenv
import os
from anthropic_api import generate_response
from utils import format_message, truncate_message, split_long_message, sanitize_input
from auth import (
    is_authenticated, authenticate_user, save_user_history, load_user_history, AUTH_CODE, save_user_scenario, load_user_scenario,
    archive_user_history, is_new_user, set_history_messages_count, get_history_messages_count
)
from scenarios import SCENARIOS
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

API_TIMEOUT = 30

class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []

    async def wait(self):
        now = time.time()
        self.calls = [call for call in self.calls if call > now - self.period]
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            logger.info(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        self.calls.append(now)

rate_limiter = RateLimiter(max_calls=5, period=60)  # 5 calls per minute

def get_user_name(user):
    if user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.first_name

def get_common_actions_keyboard():
    keyboard = [
        [InlineKeyboardButton("Change Scenario", callback_data='change_scenario'),
         InlineKeyboardButton("Clear History", callback_data='clear_history')],
        [InlineKeyboardButton("Help", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((NetworkError, TimedOut)),
    reraise=True
)
async def send_message_with_retry(context, chat_id, text, reply_markup=None):
    try:
        formatted_text = format_message(text)
        if len(formatted_text) > 4096:
            parts = split_long_message(formatted_text)
            for part in parts:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=formatted_text,
                parse_mode='MarkdownV2',
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        truncated_text = truncate_message(text)
        await context.bot.send_message(
            chat_id=chat_id,
            text=truncated_text,
            reply_markup=reply_markup
        )

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((NetworkError, TimedOut)),
    reraise=True
)
async def rate_limited_generate_response(messages, system_message):
    await rate_limiter.wait()
    return await generate_response(messages, system_message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    if is_authenticated(user_id):
        scenario = load_user_scenario(user_id)
        context.user_data['scenario'] = scenario
        context.user_data['messages'] = load_user_history(user_id, scenario)

        message = (
            f"Welcome back, {user_name}! 🎭\n\n"
            f"You're currently chatting with your '{scenario}'. Ready for some engaging conversation?\n\n"
            f"Remember, you can change who you're talking to anytime with the 'Change Scenario' button below.\n\n"
            f"Now, what would you like to chat about with your {scenario}? 😃"
        )

        await send_message_with_retry(context, update.effective_chat.id, message, reply_markup=get_common_actions_keyboard())
    else:
        await send_message_with_retry(context, update.effective_chat.id, f"Greetings, {user_name}! 🌟 To start chatting with Evander please provide the secret code. What's the password?")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, f"I'm sorry, {user_name}, but I can only assist authenticated users. Please provide the secret code first.")
        return

    help_text = """
    Here are the available actions:
    • Change Scenario - Switch to a different character to talk to
    • Clear History - Reset your conversation history (use with caution!)
    • Help - Show this help message
    • /set_history_count <number> - Set the number of history messages to load
    • /status - Display current scenario, history count, and other information

    You can also send me any message, and I'll respond based on the current scenario!
    """
    await send_message_with_retry(context, update.effective_chat.id, help_text, reply_markup=get_common_actions_keyboard())


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, f"I'm sorry, {user_name}, but I can only assist authenticated users. Please provide the secret code first.")
        return

    for scenario in SCENARIOS.keys():
        archive_user_history(user_id, scenario)

    context.user_data['messages'] = []
    context.user_data['scenario'] = load_user_scenario(user_id)

    await send_message_with_retry(context, update.effective_chat.id, "All your conversation histories across all scenarios have been reset. you are currently chatting with your '{}'.".format(context.user_data['scenario']), reply_markup=get_common_actions_keyboard())

async def change_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, f"I'm sorry, {user_name}, but I can only assist authenticated users. Please provide the secret code first.")
        return

    keyboard = [
        [InlineKeyboardButton("Demon Slayer", callback_data='demon_slayer'),
         InlineKeyboardButton("Boyfriend", callback_data='boyfriend')],
        [InlineKeyboardButton("Best Friend", callback_data='best_friend'),
         InlineKeyboardButton("Mentor", callback_data='mentor')],
        [InlineKeyboardButton("Sibling", callback_data='sibling'),
         InlineKeyboardButton("Coach", callback_data='coach')],
        [InlineKeyboardButton("Guidance Counselor", callback_data='guidance_counselor'),
         InlineKeyboardButton("Cpp Expert", callback_data='cpp_expert')],
        [InlineKeyboardButton("Socratic Tutor", callback_data='socratic_tutor'),
        InlineKeyboardButton("Mental Health Advocate", callback_data='mental_health_advocate')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Choose who you'd like to talk to:\n\n"
             "🗡️ Demon Slayer: Chat with a brave warrior from Taisho-era Japan\n"
             "💑 Boyfriend: Talk to your caring high school boyfriend\n"
             "🤝 Best Friend: Hang out with your supportive and fun-loving best friend, Tiffany\n"
             "📚 Mentor: Seek wisdom from your high school teacher\n"
             "👶 Sibling: Play with your 6-year-old younger brother\n"
             "🏋️ Coach: Get motivated by your dedicated high school sports coach\n"
             "🧠 Guidance Counselor: Discuss your concerns with the school counselor\n"
             "🧠 cpp Expert: Learn about C++ programming language\n\n"
             "🎓 Socratic Tutor: Learn through guided questioning\n\n"
             "💚 Mental Health Advocate: Talk to a compassionate mental health professional\n\n"
             "Select an option to change who you're talking to:",
        reply_markup=reply_markup
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'change_scenario':
        await change_scenario(update, context)
    elif query.data == 'clear_history':
        await clear_command(update, context)
    elif query.data == 'help':
        await help_command(update, context)
    else:
        # Handle scenario changes
        user_id = update.effective_user.id
        new_scenario = query.data
        old_scenario = context.user_data.get('scenario', 'boyfriend')
        context.user_data['scenario'] = new_scenario
        context.user_data['messages'] = load_user_history(user_id, new_scenario)
        save_user_scenario(user_id, new_scenario)

        scenario_descriptions = {
            'demon_slayer': "Demon Slayer - You're now chatting with a brave warrior from early 20th century Japan!",
            'boyfriend': "Boyfriend - You're now talking to your caring high school boyfriend!",
            'best_friend': "Best Friend - You're now hanging out with your supportive and fun-loving best friend, Tiffany!",
            'mentor': "Mentor - You're now seeking wisdom from your high school teacher!",
            'sibling': "Sibling - You're now playing with your 6-year-old younger brother!",
            'coach': "Coach - You're now getting motivated by your dedicated high school sports coach!",
            'guidance_counselor': "Guidance Counselor - You're now discussing your concerns with the school counselor!",
            'cpp_expert': "C++ Expert - You're now talking to a skilled C++ developer!",
            'socratic_tutor': "Socratic Tutor - You're now learning through guided questioning!",
            'mental_health_advocate': "Mental Health Advocate - You're now talking to a compassionate mental health professional!",
        }

        await query.edit_message_text(
            text=f"You've switched from talking to your {old_scenario} to your {scenario_descriptions[new_scenario]}\n\n"
            f"Your conversation history has been updated to match. Enjoy chatting!",
            reply_markup=get_common_actions_keyboard()
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    user_message = sanitize_input(update.message.text)
    chat_id = update.effective_chat.id

    logger.info(f"Received message from user {user_id} ({user_name}): {user_message[:20]}...")

    if not is_authenticated(user_id):
        if user_message == AUTH_CODE:
            authenticate_user(user_id)
            scenario = load_user_scenario(user_id)
            context.user_data['scenario'] = scenario
            context.user_data['messages'] = load_user_history(user_id, scenario)

            if is_new_user(user_id):
                welcome_message = (
                    f"Welcome to Evander, {user_name}! 🎉\n\n"
                    f"I'm an AI-powered bot created by Mark Llego, capable of taking on various roles to chat with you. "
                    f"Your current scenario is '{scenario}'.\n\n"
                    f"You can change who you're talking to anytime using the 'Change Scenario' button below. "
                    f"Feel free to ask me anything or just chat casually!\n\n"
                    f"Enjoy your time with Mark Llego's AI companion! 😊"
                )
                await send_message_with_retry(context, chat_id, welcome_message, reply_markup=get_common_actions_keyboard())
            else:
                message = (
                    f"Welcome back, {user_name}! You're now authenticated. "
                    f"Your current scenario is {scenario}. "
                    f"You can start chatting now."
                )
                await send_message_with_retry(context, chat_id, message, reply_markup=get_common_actions_keyboard())
        else:
            await send_message_with_retry(context, chat_id, f"I'm sorry, {user_name}, but I can only assist authenticated users. Please provide the secret code.")
        return

    if 'messages' not in context.user_data:
        scenario = load_user_scenario(user_id)
        context.user_data['scenario'] = scenario
        context.user_data['messages'] = load_user_history(user_id, scenario)

    context.user_data['messages'].append({"role": "user", "content": user_message})

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        scenario = context.user_data['scenario']
        system_message = SCENARIOS[scenario]

        start_time = time.time()
        response = await rate_limited_generate_response(context.user_data['messages'], system_message)
        end_time = time.time()

        response_time = end_time - start_time
        logger.info(f"API response time: {response_time:.2f} seconds")

        context.user_data['messages'].append({"role": "assistant", "content": response})

        asyncio.create_task(save_user_history(user_id, context.user_data['messages'], scenario))

        await send_message_with_retry(context, chat_id, response)

        logger.info(f"Sent response to user {user_id} ({user_name}): {response[:20]}...")

    except Exception as e:
        logger.error(f"Error handling message for user {user_id} ({user_name}): {str(e)}", exc_info=True)
        error_message = f"I apologize, {user_name}, but I've encountered an error while processing your request. Please try again later."
        await send_message_with_retry(context, chat_id, error_message)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    error_message = "Sorry, something went wrong. Please try again later."
    if isinstance(context.error, NetworkError):
        error_message = "Network error occurred. Please check your connection."
    elif isinstance(context.error, TimedOut):
        error_message = "Request timed out. Please try again."

    if update and update.effective_chat:
        user_name = get_user_name(update.effective_user) if update.effective_user else "User"
        await send_message_with_retry(context, update.effective_chat.id, f"{user_name}, {error_message}")

# Add this new command handler function
async def set_history_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, f"I'm sorry, {user_name}, but I can only assist authenticated users. Please provide the secret code first.")
        return

    if not context.args or not context.args[0].isdigit():
        await send_message_with_retry(context, update.effective_chat.id, "Please provide a valid number of messages to load from history.")
        return

    count = int(context.args[0])
    set_history_messages_count(count)
    await send_message_with_retry(context, update.effective_chat.id, f"History messages count has been set to {get_history_messages_count}.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = get_user_name(update.effective_user)
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, f"I'm sorry, {user_name}, but I can only assist authenticated users. Please provide the secret code first.")
        return

    current_scenario = context.user_data.get('scenario', load_user_scenario(user_id))
    history_count = get_history_messages_count()
    message_count = len(context.user_data.get('messages', []))

    status_message = (
        f"📊 Current Status:\n\n"
        f"👤 User: {user_name}\n"
        f"🎭 Current Scenario: {current_scenario}\n"
        f"🔢 History Messages Count: {history_count}\n"
        f"💬 Current Conversation Messages: {message_count}\n"
    )
    await send_message_with_retry(context, update.effective_chat.id, status_message, reply_markup=get_common_actions_keyboard())

def main():
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    application.add_handler(CommandHandler("set_history_count", set_history_count))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("status", status_command)) 
    application.add_handler(CommandHandler("scenario", change_scenario))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button))
    application.add_error_handler(error_handler)
    application.run_polling(poll_interval=1.0, timeout=30)

if __name__ == '__main__':
    main()
