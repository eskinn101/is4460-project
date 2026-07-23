# Moderation

Django website foundation for a health coaching platform focused on customer health records, employee-managed recommendation data, and basic analytics for diet, exercise, wellness, and meal tracking.

## Included features

- Django authentication with separate customer and employee access
- Customer health profiles, goals, meal entries, and chat history stored in SQLite
- Employee recommendation management with analytics-focused recommendation fields
- Health analytics such as consistency scoring, calorie totals, and behavior insights
- Protected multi-page interface for customer hub, employee hub, chat, health, and meals

## Seeded accounts

- Customer: `jordan@moderation.app` / `customer-demo`
- Employee: `coach@moderation.app` / `employee-demo`

## Optional AI setup

Set one of the following environment variables to enable API-backed guidance:

- `GEMNI_API_KEY` or `GEMINI_API_KEY` if that is the name already used in your repo
- `OPENAI_API_KEY` or `MODERATION_AI_API_KEY`
- Optional: `OPENAI_BASE_URL` or `MODERATION_AI_BASE_URL` for OpenAI-compatible providers
- Optional: `MODERATION_AI_MODEL` to override the default model name

When no key is configured, the app falls back to the existing local analytics and recommendation logic.

## Run locally

```bash
python3 -m pip install django
python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runserver
```

Then open `http://127.0.0.1:8000`.