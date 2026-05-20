# 🍳 ChefAI Discord Bot

A Discord bot powered by Claude AI that helps with ingredient management and recipe recommendations.

## Features

- 🧺 **Pantry Management** — track your ingredients per user
- 🍽️ **Recipe Recommendations** — get recipes based on what you have
- 🔄 **Ingredient Substitutes** — find alternatives for any ingredient
- 📅 **Meal Planning** — generate multi-day meal plans
- 💬 **Free Chat** — mention the bot to ask anything cooking-related

## Setup

1. Clone the repo
```bash
git clone https://github.com/rnguon/chef-ai-bot.git
cd chef-ai-bot
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Create a `.env` file
```env
DISCORD_TOKEN=your_discord_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key
```

4. Run the bot
```bash
python bot.py
```

## Commands

| Command | Description |
|---|---|
| `!add <ingredients>` | Add ingredients (comma-separated) |
| `!remove <ingredient>` | Remove an ingredient |
| `!pantry` | View your ingredient list |
| `!clear` | Clear your pantry |
| `!recipe` | Get recipes from your pantry |
| `!recipe <dish>` | Get a specific recipe |
| `!substitute <ingredient>` | Find ingredient substitutes |
| `!mealplan [days]` | Generate a meal plan (1–7 days) |
| `!chef <question>` | Ask anything about cooking |
| `!chefhelp` | Show help |

## Requirements

- Python 3.10+
- Discord bot token with **Message Content Intent** enabled
- Anthropic API key
