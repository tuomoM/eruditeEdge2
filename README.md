# eruditeEdge2


eruditeEdge2 is a version of eruditeEdge planned to fullfil and actual need and to be run not on rapserry, but likely on a dedicated domain.
This version is almost entirely written using Open AI Codex.

# Project website
 [eruditeEdge](https://erudite-edge.com)

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
* Possiblity to delete invite codes for admin
* Possibility to delete users by admin
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
SECURITY_REPORT_DIR=
SECURITY_REPORT_PATH=
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4.1-mini
TRUSTED_AI_DAILY_QUOTA=20
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_REDIRECT_SCHEME=
```

`OPENAI_API_KEY` is only needed for AI vocabulary generation. The rest of the app works without it. Leave `DATABASE` empty for local development unless you want to store `database.db` somewhere else.
Leave `SECURITY_REPORT_DIR` and `SECURITY_REPORT_PATH` empty to read `security-report.json` from the project root. Set `SECURITY_REPORT_DIR` to a persistent directory to read and write `security-report.json` from that location, for example the same directory as the production database. Set `SECURITY_REPORT_PATH` only when you need to point at an exact report file path. Admin users can generate the report from the admin page.
Google OAuth callback URLs use HTTPS automatically outside localhost. Set `GOOGLE_REDIRECT_SCHEME=http` only for a local OAuth test client that explicitly needs HTTP callbacks.

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

In production, point persistent files at `./data`. The `./app` directory is not persistent, so do not store the database or security report there. If `DATABASE` is not set and `RAILWAY_VOLUME_MOUNT_PATH` exists, the app uses `RAILWAY_VOLUME_MOUNT_PATH/database.db` automatically. You can also set paths explicitly, for example:

```text
DATABASE=./data/database.db
SECURITY_REPORT_DIR=./data
```

The `check-database` command fails on Railway if no persistent database path is configured.

8. Run database migrations:

```bash
flask --app app migrate
```

Run this after pulling or deploying code that includes new files in
`migrations/`. The command uses Python's built-in SQLite support, records applied
migrations in `schema_migrations`, and safely stamps schema changes that were
applied manually before the migration ledger existed.

On Railway, open a shell for the deployed service after the automatic deploy and
run:

```bash
flask --app app migrate
```

The `sqlite3` command-line tool does not need to be installed in the container.
The command uses the configured production database path, including
`$RAILWAY_VOLUME_MOUNT_PATH/database.db` when `DATABASE` is not set.

9. Run tests:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

10. Create a new admin user:

```bash
flask --app app create-admin
```

The command prompts for a user id and password. When the new admin is created, all existing admin users are moved to the `trusted` category.
