# eruditeEdge2


eruditeEdge2 is a version of eruditeEdge planned to fullfil and actual need and to be run not on rapserry, but likely on a dedicated domain.
This version is almost entirely written using Open AI Codex.

# Features

* it is possible to register a user
* it is possible to log on with an existing user
* it is possible to create a vocabulary entry
* it is possible to complete the vocabulary entry using Open AI
* it is possible to search for a vocabulary entry using the word 
* Rudimentary UI defined and implemented
* possiblity to choose vocabs for training session, saving the session and successrate
* Graphical look and feel
* Handling for user levels
* Admin cockpit with possiblity to remove user and users vocabs
* google login option
* invite code functionality
* ability for a user candidate to ask for invite code


# to-do's
* Final look and feel + eruditeEdge 2 logos etc
* Hardening for internet use
* Possibility to create issues / improvement ideas



# installation

These steps assume Python 3 is installed and that commands are run from the project root.

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Create the local environment file:

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```text
SECRET_KEY=replace-with-a-local-secret
DATABASE=
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4.1-mini
TRUSTED_AI_DAILY_QUOTA=20
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
```

`OPENAI_API_KEY` is only needed for AI vocabulary generation. The rest of the app works without it. Leave `DATABASE` empty for local development unless you want to store `database.db` somewhere else.

4. Initialize the database:

```bash
python -c "from app import create_app; from db import init_db; init_db(create_app())"
```

This creates `database.db` using `schema.sql`.

5. Optional: load sample vocabulary entries:

```bash
sqlite3 database.db < sample_vocabs.sql
```

6. Start the application:

```bash
flask --app app run --port 5001
```

Open the app at `http://127.0.0.1:5001`.

7. Check the active database path:

```bash
flask --app app check-database
```

On Railway, attach a persistent volume. If `DATABASE` is not set, the app uses `RAILWAY_VOLUME_MOUNT_PATH/database.db` automatically. You can also set `DATABASE` explicitly, for example:

```text
DATABASE=/app/data/database.db
```

The `check-database` command fails on Railway if no persistent database path is configured.

8. Run tests:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

9. Create a new admin user:

```bash
flask --app app create-admin
```

The command prompts for a user id and password. When the new admin is created, all existing admin users are moved to the `trusted` category.

If you already have an older local `database.db`, back it up before applying schema changes. Existing training schema upgrades can be applied with:

```bash
sqlite3 database.db ".read migrations/001_training_quiz.sql"
sqlite3 database.db ".read migrations/002_user_account_categories.sql"
sqlite3 database.db ".read migrations/003_ai_generation_usage.sql"
sqlite3 database.db ".read migrations/004_invite_codes.sql"
sqlite3 database.db ".read migrations/005_invite_code_usage.sql"
sqlite3 database.db ".read migrations/006_google_registration.sql"
sqlite3 database.db ".read migrations/007_access_requests.sql"
sqlite3 database.db ".read migrations/008_access_request_guardrails.sql"
sqlite3 database.db ".read migrations/009_access_request_unique_email.sql"
```
