# .flaskenv - Variables used by the 'flask' command line tool

# Points to the application factory function in app/__init__.py
# Format: <module_path>:<factory_function_call>
FLASK_APP=app:create_app()

# Sets the default environment if FLASK_ENV is not set elsewhere (e.g., in .env or system env)
# Options: development, production, testing
FLASK_ENV=development

# Optional: Explicitly enable debug mode for 'flask run' (also enabled by FLASK_ENV=development)
# FLASK_DEBUG=1