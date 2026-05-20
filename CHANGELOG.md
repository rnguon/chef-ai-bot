# Changelog

## [1.1.0] - 2026-05-20

### Added
- Recipe database (`recipes.json`) for storing favorite recipes per user
- `!saverecipe <dish>` — generate and save a recipe to favorites
- `!favorites` — list all saved favorite recipes
- `!getrecipe <name>` — retrieve a saved recipe (supports partial name matching)
- `!searchrecipe <keyword>` — search saved recipes by ingredient or keyword
- `!deleterecipe <name>` — remove a recipe from favorites
- Updated `!chefhelp` to include new recipe DB commands

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
