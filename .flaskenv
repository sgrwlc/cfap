# Variables used by the 'flask' command line tool

# Points to the application factory in app/__init__.py
FLASK_APP=app:create_app()

# Sets the environment (influences config loading)
# Can be overridden by FLASK_ENV in .env or system environment variables
FLASK_ENV=development
# FLASK_DEBUG=1 # Optional: Explicitly enable debug mode for flask run