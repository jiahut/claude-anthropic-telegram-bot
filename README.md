# claude-anthropic-telegram-bot

This Telegram bot was created as a fun and interactive chat companion for my daughter, Argi. It uses the Anthropic API to generate responses and can switch between various scenarios, providing a diverse and engaging conversational experience.

![Anthropic Claude Telegram Bot](/images/image1.png)
![Anthropic Claude Telegram Bot](/images/image2.png)

**Note: This bot is not recommended for production use. It was built as a proof of concept and for personal enjoyment.**

## Features
- Multiple chat scenarios (Demon Slayer, Boyfriend, Best Friend, Mentor, Sibling, Coach, Guidance Counselor, Socratic Tutor)
- User authentication
- Conversation history management
- Dynamic scenario switching
- Error handling and retry logic

## Prerequisites
- Python 3.12+
- Telegram Bot Token (obtained from the BotFather on Telegram): https://core.telegram.org/bots/tutorial
- Anthropic API Key: https://console.anthropic.com/dashboard

## Installation
1. Clone this repository:
   ```
   git clone https://github.com/llegomark/claude-anthropic-telegram-bot
   cd claude-anthropic-telegram-bot
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root and add your Telegram Bot Token and Anthropic API Key:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ANTHROPIC_API_KEY=your_anthropic_api_key
   AUTH_CODE=your_secret_auth_code
   ```

## Usage
1. Run the bot:
   ```
   python bot.py
   ```

2. Start a conversation with the bot on Telegram.
3. Use the `/start` command to begin and provide the secret authentication code.
4. Use `/scenario` to switch between different chat scenarios.
5. Enjoy conversing with the bot!

## Commands
- `/start`: Start a new conversation
- `/help`: Show the help message
- `/clear`: Clear all conversation histories
- `/scenario`: Change the current chat scenario

## Security Notice
- The bot uses a simple authentication mechanism and stores conversation histories locally. This may not be secure for sensitive information.
- Ensure that the `.env` file containing sensitive keys is not shared or committed to version control.

## Contributing
Contributions are welcome! Feel free to submit a pull request or open an issue. For major changes, please open an issue first to discuss what you would like to change.