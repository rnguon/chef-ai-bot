import discord
from discord.ext import commands
import anthropic
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

INGREDIENTS_FILE = Path(__file__).parent / "ingredients.json"

SYSTEM_PROMPT = """You are ChefAI, a friendly and knowledgeable culinary assistant on Discord. You specialize in:
- Recipe recommendations based on available ingredients
- Ingredient substitutions and pantry management
- Cooking techniques, tips, and tricks
- Meal planning and nutrition advice

Keep responses concise and Discord-friendly (use emojis and markdown formatting). When suggesting recipes, be specific with quantities and steps. Always be encouraging and enthusiastic about cooking!"""


def load_ingredients() -> dict:
    if INGREDIENTS_FILE.exists():
        with open(INGREDIENTS_FILE) as f:
            return json.load(f)
    return {}


def save_ingredients(data: dict) -> None:
    with open(INGREDIENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def ask_claude(user_message: str, max_tokens: int = 1024) -> str:
    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


async def send_long(ctx_or_channel, text: str, reply_to=None) -> None:
    chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
    for i, chunk in enumerate(chunks):
        if i == 0 and reply_to:
            await reply_to.reply(chunk)
        else:
            channel = getattr(ctx_or_channel, "channel", ctx_or_channel)
            await channel.send(chunk)


@bot.event
async def on_ready():
    print(f"🍳 ChefAI is online as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="recipes | !chefhelp"
        )
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        content = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if content:
            async with message.channel.typing():
                reply = ask_claude(content)
                await send_long(message.channel, reply, reply_to=message)
            return
    await bot.process_commands(message)


@bot.command(name="add")
async def add_ingredient(ctx: commands.Context, *, ingredients: str):
    data = load_ingredients()
    user_id = str(ctx.author.id)
    data.setdefault(user_id, [])
    items = [i.strip() for i in ingredients.split(",") if i.strip()]
    added, skipped = [], []
    for item in items:
        if item.lower() in [x.lower() for x in data[user_id]]:
            skipped.append(item)
        else:
            data[user_id].append(item)
            added.append(item)
    save_ingredients(data)
    lines = []
    if added:
        lines.append(f"✅ Added: **{', '.join(added)}**")
    if skipped:
        lines.append(f"⚠️ Already in pantry: {', '.join(skipped)}")
    await ctx.reply("\n".join(lines))


@bot.command(name="remove")
async def remove_ingredient(ctx: commands.Context, *, ingredient: str):
    data = load_ingredients()
    user_id = str(ctx.author.id)
    if not data.get(user_id):
        await ctx.reply("❌ Your pantry is empty!")
        return
    before = len(data[user_id])
    data[user_id] = [i for i in data[user_id] if i.lower() != ingredient.strip().lower()]
    if len(data[user_id]) < before:
        save_ingredients(data)
        await ctx.reply(f"🗑️ Removed **{ingredient}** from your pantry.")
    else:
        await ctx.reply(f"⚠️ **{ingredient}** wasn't found in your pantry.")


@bot.command(name="clear")
async def clear_pantry(ctx: commands.Context):
    data = load_ingredients()
    user_id = str(ctx.author.id)
    data[user_id] = []
    save_ingredients(data)
    await ctx.reply("🧹 Your pantry has been cleared!")


@bot.command(name="pantry")
async def list_pantry(ctx: commands.Context):
    data = load_ingredients()
    user_id = str(ctx.author.id)
    items = data.get(user_id, [])
    if not items:
        await ctx.reply("🧺 Your pantry is empty! Use `!add <ingredient>` to stock up.")
        return
    bullet_list = "\n".join(f"• {i}" for i in items)
    await ctx.reply(f"🧺 **Your Pantry** ({len(items)} items):\n{bullet_list}")


@bot.command(name="recipe")
async def recipe(ctx: commands.Context, *, dish: str = None):
    data = load_ingredients()
    user_id = str(ctx.author.id)
    items = data.get(user_id, [])
    if dish:
        prompt = f"Give me a detailed recipe for **{dish}**."
        if items:
            prompt += f" I have these ingredients available: {', '.join(items)}. Suggest substitutions if I'm missing anything."
    elif items:
        prompt = (f"I have these ingredients in my pantry: {', '.join(items)}. "
                  "Suggest 2-3 recipes I can make with them, with a short description and key steps for each.")
    else:
        await ctx.reply("🧺 Your pantry is empty!\n• Add ingredients with `!add chicken, garlic, pasta`\n• Or request a specific recipe: `!recipe spaghetti carbonara`")
        return
    async with ctx.typing():
        reply = ask_claude(prompt, max_tokens=1500)
        await send_long(ctx, reply, reply_to=ctx.message)


@bot.command(name="chef")
async def chef(ctx: commands.Context, *, question: str):
    async with ctx.typing():
        reply = ask_claude(question)
        await send_long(ctx, reply, reply_to=ctx.message)


@bot.command(name="substitute")
async def substitute(ctx: commands.Context, *, ingredient: str):
    async with ctx.typing():
        prompt = (f"What are the best substitutes for **{ingredient}** in cooking? "
                  "Give 3-4 options with brief explanations of when each works best.")
        reply = ask_claude(prompt, max_tokens=600)
        await send_long(ctx, reply, reply_to=ctx.message)


@bot.command(name="mealplan")
async def meal_plan(ctx: commands.Context, days: int = 3):
    days = max(1, min(days, 7))
    data = load_ingredients()
    user_id = str(ctx.author.id)
    items = data.get(user_id, [])
    if not items:
        await ctx.reply("🧺 Add some ingredients first with `!add <ingredient>`!")
        return
    async with ctx.typing():
        prompt = (f"Create a {days}-day meal plan (breakfast, lunch, dinner) using these ingredients: "
                  f"{', '.join(items)}. Keep it practical and varied.")
        reply = ask_claude(prompt, max_tokens=2000)
        await send_long(ctx, reply, reply_to=ctx.message)


@bot.command(name="chefhelp")
async def chef_help(ctx: commands.Context):
    embed = discord.Embed(
        title="🍳 ChefAI — Your Culinary Assistant",
        description="Mention me (@ChefAI) anytime to chat, or use the commands below!",
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="🧺 Pantry Management",
        value=("`!add <ingredient(s)>` — Add ingredients (comma-separated)\n"
               "`!remove <ingredient>` — Remove an ingredient\n"
               "`!pantry` — View your ingredient list\n"
               "`!clear` — Clear your pantry"),
        inline=False,
    )
    embed.add_field(
        name="🍽️ Recipes & Cooking",
        value=("`!recipe` — Get recipes from your pantry\n"
               "`!recipe <dish>` — Get a specific recipe\n"
               "`!substitute <ingredient>` — Find ingredient substitutes\n"
               "`!mealplan [days]` — Generate a meal plan (1–7 days)\n"
               "`!chef <question>` — Ask anything about cooking"),
        inline=False,
    )
    embed.set_footer(text="Powered by Claude AI 🤖")
    await ctx.reply(embed=embed)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
