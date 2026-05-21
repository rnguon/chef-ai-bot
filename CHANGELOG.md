# Changelog

## [1.2.0] - 2026-05-20

### Changed
- Recipe files are now stored as structured JSON (`.json`) instead of markdown (`.md`)
- Each recipe file follows a defined schema with: id, title, description, author, tags, servings, prep/cook time, ingredients (with quantity + unit), step-by-step instructions, nutrition, and timestamps
- `!saverecipe` prompts Claude to return the full schema as JSON
- `!getrecipe` formats JSON fields into a readable Discord message
- `!searchrecipe` searches JSON content in addition to the index

## [1.1.0] - 2026-05-20

### Added
- Recipe database with per-user files (`recipes/{user_id}/{slug}.json`)
- `recipes.json` as a lightweight index storing: name, tags, ingredients, file reference, saved_at
- `!saverecipe <dish>` — Claude generates recipe, extracts ingredients & tags, saves as file
- `!favorites` — lists saved recipes with tags and save date
- `!getrecipe <name>` — reads and displays the recipe file (partial name matching)
- `!searchrecipe <keyword>` — searches index (name, tags, ingredients) and file content
- `!deleterecipe <name>` — removes both the file and index entry
- Updated `!chefhelp` embed with Favorite Recipes section

## [1.0.0] - 2026-05-20

### Added
- Initial release of ChefAI Discord bot
- Per-user pantry management (`!add`, `!remove`, `!pantry`, `!clear`)
- Recipe recommendations based on pantry ingredients (`!recipe`)
- Specific recipe lookup (`!recipe <dish>`)
- Ingredient substitution suggestions (`!substitute`)
- Multi-day meal plan generation (`!mealplan`)
- Free chat via `@ChefAI` mentions or `!chef`
- Prompt caching on system prompt for faster API responses
