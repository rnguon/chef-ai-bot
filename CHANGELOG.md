# Changelog

## [1.1.0] - 2026-05-20

### Added
- Recipe database with per-user markdown files (`recipes/{user_id}/{slug}.md`)
- `recipes.json` as a lightweight index storing: name, tags, ingredients, file reference, saved_at
- `!saverecipe <dish>` — Claude generates recipe, extracts ingredients & tags, saves as markdown
- `!favorites` — lists saved recipes with tags and save date
- `!getrecipe <name>` — reads and displays the full markdown recipe file (partial name matching)
- `!searchrecipe <keyword>` — searches index (name, tags, ingredients) and file content
- `!deleterecipe <name>` — removes both the markdown file and index entry
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
