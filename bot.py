import discord
from discord.ext import commands
import anthropic
import json
import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

INGREDIENTS_FILE = Path(__file__).parent / "ingredients.json"
RECIPES_FILE = Path(__file__).parent / "recipes.json"
RECIPES_DIR = Path(__file__).parent / "recipes"

SYSTEM_PROMPT = """You are ChefAI, a friendly and knowledgeable culinary assistant on Discord. You specialize in:
- Recipe recommendations based on available ingredients
- Ingredient substitutions and pantry management
- Cooking techniques, tips, and tricks
- Meal planning and nutrition advice

Keep responses concise and Discord-friendly (use emojis and markdown formatting). When suggesting recipes, be specific with quantities and steps. Always be encouraging and enthusiastic about cooking!"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert a recipe name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '_', slug)
    return slug.strip('_')


def load_ingredients() -> dict:
    if INGREDIENTS_FILE.exists():
        with open(INGREDIENTS_FILE) as f:
            return json.load(f)
    return {}


def save_ingredients(data: dict) -> None:
    with open(INGREDIENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_recipes() -> dict:
    """Load the recipe index (metadata only)."""
    if RECIPES_FILE.exists():
        with open(RECIPES_FILE) as f:
            return json.load(f)
    return {}


def save_recipe_index(data: dict) -> None:
    with open(RECIPES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user_recipes(user_id: str) -> dict:
    return load_recipes().get(user_id, {})


def read_recipe_file(file_path: str) -> str | None:
    """Read the full recipe markdown from disk."""
    path = Path(__file__).parent / file_path
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    print(f"🍳 ChefAI is online as {bot.user} (ID: {bot.user.id})")
    RECIPES_DIR.mkdir(exist_ok=True)
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


# ---------------------------------------------------------------------------
# Commands — Pantry management
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Commands — AI-powered cooking
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Commands — Recipe database
# ---------------------------------------------------------------------------

@bot.command(name="saverecipe")
async def save_recipe(ctx: commands.Context, *, dish: str):
    """Generate and save a recipe as a markdown file; index it in recipes.json."""
    async with ctx.typing():
        prompt = (
            f'Generate a complete recipe for "{dish}". '
            'Return ONLY a valid JSON object with these exact keys (no markdown code blocks):\n'
            '- "markdown": the full recipe in markdown with # Title, ## Description, ## Ingredients, ## Instructions sections\n'
            '- "ingredients": list of main ingredient names only (no quantities)\n'
            '- "tags": list of 3-5 tags (cuisine, protein, meal type, diet, etc.)\n\n'
            'Example: {"markdown": "# Pasta\\n...", "ingredients": ["pasta", "garlic"], "tags": ["italian", "dinner"]}'
        )
        raw = ask_claude(prompt, max_tokens=2000)

    # Parse JSON from Claude response
    try:
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        recipe_data = json.loads(json_match.group()) if json_match else {}
    except (json.JSONDecodeError, AttributeError):
        recipe_data = {}

    markdown = recipe_data.get("markdown") or raw
    ingredients = recipe_data.get("ingredients", [])
    tags = recipe_data.get("tags", [])

    # Save markdown file to recipes/{user_id}/{slug}.md
    user_id = str(ctx.author.id)
    slug = slugify(dish)
    user_dir = RECIPES_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    relative_path = f"recipes/{user_id}/{slug}.md"
    (Path(__file__).parent / relative_path).write_text(markdown, encoding="utf-8")

    # Update index in recipes.json
    index = load_recipes()
    index.setdefault(user_id, {})
    index[user_id][slug] = {
        "name": dish,
        "tags": tags,
        "ingredients": ingredients,
        "file": relative_path,
        "saved_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    save_recipe_index(index)

    tags_str = " ".join(f"`{t}`" for t in tags) or "none"
    ing_preview = ", ".join(ingredients[:6]) + (" ..." if len(ingredients) > 6 else "")
    await ctx.reply(
        f"❤️ **{dish}** saved to your favorites!\n"
        f"🏷️ Tags: {tags_str}\n"
        f"🧺 Key ingredients: {ing_preview or 'see recipe'}\n"
        f"📄 File: `{relative_path}`\n\n"
        f"*Use `!getrecipe {dish}` to view the full recipe.*"
    )


@bot.command(name="favorites")
async def list_favorites(ctx: commands.Context):
    """List all saved recipes from the index."""
    user_id = str(ctx.author.id)
    recipes = get_user_recipes(user_id)
    if not recipes:
        await ctx.reply("📖 No saved recipes yet! Use `!saverecipe <dish>` to save one.")
        return

    lines = [f"📖 **Your Favorite Recipes** ({len(recipes)} saved):\n"]
    for i, (slug, r) in enumerate(recipes.items(), 1):
        tag_str = " ".join(f"`{t}`" for t in r.get("tags", []))
        lines.append(f"`{i}.` **{r['name']}** {tag_str}\n    └ Saved {r['saved_at']}")
    lines.append("\n*Use `!getrecipe <name>` to view a recipe.*")
    await ctx.reply("\n".join(lines))


@bot.command(name="getrecipe")
async def get_recipe(ctx: commands.Context, *, dish: str):
    """Retrieve a full recipe from its markdown file."""
    user_id = str(ctx.author.id)
    recipes = get_user_recipes(user_id)
    key = slugify(dish)

    # Exact slug match, then partial
    entry = recipes.get(key) or next(
        (v for k, v in recipes.items() if dish.lower() in k), None
    )

    if not entry:
        await ctx.reply(f"❌ **{dish}** not found. Use `!favorites` to see your saved recipes.")
        return

    content = read_recipe_file(entry["file"])
    if not content:
        await ctx.reply(f"⚠️ Recipe file missing for **{entry['name']}**. Try saving it again with `!saverecipe {entry['name']}`.")
        return

    await send_long(ctx, content, reply_to=ctx.message)


@bot.command(name="deleterecipe")
async def delete_recipe(ctx: commands.Context, *, dish: str):
    """Delete a recipe's markdown file and remove it from the index."""
    index = load_recipes()
    user_id = str(ctx.author.id)
    recipes = index.get(user_id, {})
    key = slugify(dish)

    match_key = key if key in recipes else next(
        (k for k in recipes if dish.lower() in k), None
    )
    if not match_key:
        await ctx.reply(f"❌ **{dish}** not found in your favorites.")
        return

    entry = recipes.pop(match_key)
    index[user_id] = recipes
    save_recipe_index(index)

    # Delete the markdown file
    file_path = Path(__file__).parent / entry["file"]
    if file_path.exists():
        file_path.unlink()

    await ctx.reply(f"🗑️ Removed **{entry['name']}** and its recipe file.")


@bot.command(name="searchrecipe")
async def search_recipe(ctx: commands.Context, *, keyword: str):
    """Search saved recipes by ingredient, tag, or keyword (searches index + file content)."""
    user_id = str(ctx.author.id)
    recipes = get_user_recipes(user_id)
    if not recipes:
        await ctx.reply("📖 No saved recipes yet!")
        return

    kw = keyword.lower()
    matches = []
    for slug, r in recipes.items():
        in_name = kw in r["name"].lower()
        in_tags = any(kw in t.lower() for t in r.get("tags", []))
        in_ingredients = any(kw in i.lower() for i in r.get("ingredients", []))
        in_file = kw in (read_recipe_file(r["file"]) or "").lower()
        if in_name or in_tags or in_ingredients or in_file:
            matches.append(r)

    if not matches:
        await ctx.reply(f"🔍 No recipes found matching **{keyword}**.")
        return

    lines = [f"🔍 **Recipes matching '{keyword}'** ({len(matches)} found):\n"]
    for r in matches:
        tag_str = " ".join(f"`{t}`" for t in r.get("tags", []))
        ing_str = ", ".join(r.get("ingredients", [])[:4])
        lines.append(f"• **{r['name']}** {tag_str}\n    Ingredients: {ing_str}")
    lines.append("\n*Use `!getrecipe <name>` to view a recipe.*")
    await ctx.reply("\n".join(lines))


# ---------------------------------------------------------------------------
# Help command
# ---------------------------------------------------------------------------

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
    embed.add_field(
        name="❤️ Favorite Recipes",
        value=("`!saverecipe <dish>` — Generate & save a recipe\n"
               "`!favorites` — List all saved recipes with tags\n"
               "`!getrecipe <name>` — View a full saved recipe\n"
               "`!searchrecipe <keyword>` — Search by ingredient, tag, or keyword\n"
               "`!deleterecipe <name>` — Remove a recipe and its file"),
        inline=False,
    )
    embed.set_footer(text="Powered by Claude AI 🤖")
    await ctx.reply(embed=embed)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
