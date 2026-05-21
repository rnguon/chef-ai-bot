import discord
from discord.ext import commands
import anthropic
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
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

RECIPE_SCHEMA_PROMPT = """
Return ONLY a valid JSON object (no markdown code blocks, no extra text) for the recipe with these exact fields:
{
  "id": "<slug-based-id>",
  "title": "<dish name>",
  "description": "<1-2 sentence description>",
  "author": "<discord_username>",
  "tags": ["<tag1>", "<tag2>", "..."],
  "servings": <number>,
  "prep_time_minutes": <number>,
  "cook_time_minutes": <number>,
  "ingredients": [
    { "name": "<ingredient>", "quantity": <number>, "unit": "<unit>" }
  ],
  "instructions": [
    "<step 1>",
    "<step 2>"
  ],
  "nutrition": {
    "calories": <number>,
    "protein_g": <number>,
    "fat_g": <number>,
    "carbs_g": <number>
  },
  "created_at": "<ISO8601 datetime>",
  "updated_at": "<ISO8601 datetime>"
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
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


def load_recipe_index() -> dict:
    """Load the lightweight recipe index (name, tags, ingredients, file ref)."""
    if RECIPES_FILE.exists():
        with open(RECIPES_FILE) as f:
            return json.load(f)
    return {}


def save_recipe_index(data: dict) -> None:
    with open(RECIPES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user_recipes(user_id: str) -> dict:
    return load_recipe_index().get(user_id, {})


def read_recipe_file(file_path: str) -> dict | None:
    """Read a recipe JSON file and return parsed dict."""
    path = Path(__file__).parent / file_path
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def format_recipe_for_discord(r: dict) -> str:
    """Format a recipe JSON dict into a readable Discord message."""
    lines = []

    lines.append(f"# {r.get('title', 'Recipe')}")
    if r.get('description'):
        lines.append(f"*{r['description']}*")
    lines.append("")

    meta = []
    if r.get('servings'):
        meta.append(f"🏆 Serves {r['servings']}")
    if r.get('prep_time_minutes'):
        meta.append(f"⏲️ Prep {r['prep_time_minutes']}m")
    if r.get('cook_time_minutes'):
        meta.append(f"🔥 Cook {r['cook_time_minutes']}m")
    if meta:
        lines.append("  ".join(meta))

    if r.get('tags'):
        lines.append("🏷️ " + " ".join(f"`{t}`" for t in r['tags']))
    lines.append("")

    if r.get('ingredients'):
        lines.append("**🧺 Ingredients**")
        for ing in r['ingredients']:
            qty = ing.get('quantity', '')
            unit = ing.get('unit', '')
            name = ing.get('name', '')
            lines.append(f"• {qty} {unit} {name}".strip())
    lines.append("")

    if r.get('instructions'):
        lines.append("**📝 Instructions**")
        for i, step in enumerate(r['instructions'], 1):
            lines.append(f"`{i}.` {step}")
    lines.append("")

    nutrition = r.get('nutrition', {})
    if any(nutrition.values()):
        lines.append("**📊 Nutrition (per serving)**")
        lines.append(
            f"Calories: {nutrition.get('calories', '?')} • "
            f"Protein: {nutrition.get('protein_g', '?')}g • "
            f"Fat: {nutrition.get('fat_g', '?')}g • "
            f"Carbs: {nutrition.get('carbs_g', '?')}g"
        )

    return "\n".join(lines)


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
    """Generate and save a recipe as a structured JSON file."""
    user_id = str(ctx.author.id)
    slug = slugify(dish)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with ctx.typing():
        prompt = (
            f'Generate a recipe for "{dish}" by {ctx.author.display_name}.\n'
            f'Use id "{slug}", author "{ctx.author.display_name}", '
            f'created_at and updated_at "{now}".\n'
            + RECIPE_SCHEMA_PROMPT
        )
        raw = ask_claude(prompt, max_tokens=2000)

    # Parse JSON
    try:
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        recipe_data = json.loads(json_match.group()) if json_match else {}
    except (json.JSONDecodeError, AttributeError):
        recipe_data = {}

    if not recipe_data.get("title"):
        await ctx.reply("⚠️ Failed to generate a valid recipe. Please try again.")
        return

    # Save recipe JSON file
    user_dir = RECIPES_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    relative_path = f"recipes/{user_id}/{slug}.json"
    (Path(__file__).parent / relative_path).write_text(
        json.dumps(recipe_data, indent=2), encoding="utf-8"
    )

    # Update lightweight index
    index = load_recipe_index()
    index.setdefault(user_id, {})
    index[user_id][slug] = {
        "name": recipe_data.get("title", dish),
        "tags": recipe_data.get("tags", []),
        "ingredients": [i["name"] for i in recipe_data.get("ingredients", [])],
        "file": relative_path,
        "saved_at": now,
    }
    save_recipe_index(index)

    tags_str = " ".join(f"`{t}`" for t in recipe_data.get("tags", [])) or "none"
    ing_preview = ", ".join(i["name"] for i in recipe_data.get("ingredients", [])[:5])
    total_time = recipe_data.get("prep_time_minutes", 0) + recipe_data.get("cook_time_minutes", 0)

    await ctx.reply(
        f"❤️ **{recipe_data['title']}** saved!\n"
        f"🏷️ Tags: {tags_str}\n"
        f"⏱️ Total time: {total_time} min  🏆 Serves {recipe_data.get('servings', '?')}\n"
        f"🧺 Key ingredients: {ing_preview}\n"
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
    """Retrieve and display a saved recipe from its JSON file."""
    user_id = str(ctx.author.id)
    recipes = get_user_recipes(user_id)
    key = slugify(dish)

    entry = recipes.get(key) or next(
        (v for k, v in recipes.items() if dish.lower() in k), None
    )
    if not entry:
        await ctx.reply(f"❌ **{dish}** not found. Use `!favorites` to see your saved recipes.")
        return

    recipe_data = read_recipe_file(entry["file"])
    if not recipe_data:
        await ctx.reply(f"⚠️ Recipe file missing for **{entry['name']}**. Try `!saverecipe {entry['name']}` again.")
        return

    await send_long(ctx, format_recipe_for_discord(recipe_data), reply_to=ctx.message)


@bot.command(name="deleterecipe")
async def delete_recipe(ctx: commands.Context, *, dish: str):
    """Delete a recipe JSON file and remove it from the index."""
    index = load_recipe_index()
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

    file_path = Path(__file__).parent / entry["file"]
    if file_path.exists():
        file_path.unlink()

    await ctx.reply(f"🗑️ Removed **{entry['name']}** and its recipe file.")


@bot.command(name="searchrecipe")
async def search_recipe(ctx: commands.Context, *, keyword: str):
    """Search saved recipes by ingredient, tag, or keyword."""
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
        # Also search full JSON file content
        file_data = read_recipe_file(r["file"])
        in_file = kw in json.dumps(file_data).lower() if file_data else False
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
        value=("`!saverecipe <dish>` — Generate & save a recipe as JSON\n"
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
