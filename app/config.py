# app/config.py
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Determine the base directory of the project (where .env should be)
# This assumes config.py is in app/
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Load the .env file from the project root
dotenv_path = os.path.join(basedir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"INFO: Loaded environment variables from {dotenv_path}") # Added info message
else:
    # Changed to warning log
    print(f"WARNING: .env file not found at {dotenv_path}. Using environment variables or defaults.")

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        print("WARNING: SECRET_KEY not found in environment. Using default. THIS IS INSECURE FOR PRODUCTION.")
        SECRET_KEY = 'a-default-insecure-secret-key-CHANGE-ME' # Provide a default but warn heavily

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') # Base URI loaded from .env

    # Security token for internal API calls from Asterisk
    INTERNAL_API_TOKEN = os.environ.get('INTERNAL_API_TOKEN')
    if not INTERNAL_API_TOKEN:
         print("WARNING: INTERNAL_API_TOKEN not set in environment. Internal API calls will fail authentication.")

    # Add other base configurations here (e.g., Mail settings if needed)
    # MAIL_SERVER = os.environ.get('MAIL_SERVER')

    @staticmethod
    def init_app(app):
        """Perform app-specific initialization if needed."""
        # Example: Configure logging based on environment later
        pass


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    # Use the base DATABASE_URI or provide a fallback specifically for development
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') or \
        'postgresql://call_platform_user:Sudh%403299@localhost:5432/call_platform_db' # Development fallback
    # Add development-specific settings
    SQLALCHEMY_ECHO = os.environ.get('SQLALCHEMY_ECHO', 'False').lower() in ('true', '1', 't') # Optional SQL echoing via env var
    print(f"INFO: Development mode enabled. SQLALCHEMY_ECHO={SQLALCHEMY_ECHO}")


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SECRET_KEY = 'testing-secret-key' # Fixed key for stable test sessions
    # Ensure a separate TEST_DATABASE_URI is used if possible, otherwise use the main one with caution
    # Default to a specific test DB name if TEST_DATABASE_URI isn't set in .env
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URI') or \
        os.environ.get('DATABASE_URI', '').replace('call_platform_db', 'call_platform_test_db') or \
        'postgresql://call_platform_user:Sudh%403299@localhost:5432/call_platform_test_db' # Testing fallback

    WTF_CSRF_ENABLED = False # Disable CSRF protection in tests
    SQLALCHEMY_ECHO = False # Usually disable echoing in tests unless debugging SQL
    # Suppress warnings during tests if desired
    # import warnings
    # warnings.filterwarnings("ignore", category=SomeWarningCategory)
    print("INFO: Testing mode enabled.")


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False # Explicitly set DEBUG to False
    # Ensure DATABASE_URI is set in the production environment
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI')
    if not SQLALCHEMY_DATABASE_URI:
        # Use logger if available, otherwise print and potentially exit/fail
        print("CRITICAL: DATABASE_URI not set for production environment!")
        # In a real scenario, you might raise an error here to prevent startup
        # raise ValueError("Production configuration requires DATABASE_URI to be set.")

    # Ensure SECRET_KEY is set and not the default
    if not Config.SECRET_KEY or Config.SECRET_KEY == 'a-default-insecure-secret-key-CHANGE-ME':
         print("CRITICAL: SECRET_KEY is not set or is using the default insecure value for production!")
         # raise ValueError("Production configuration requires a strong, unique SECRET_KEY.")

    # Ensure INTERNAL_API_TOKEN is set
    if not Config.INTERNAL_API_TOKEN:
        print("CRITICAL: INTERNAL_API_TOKEN is not set for production environment!")
        # raise ValueError("Production configuration requires INTERNAL_API_TOKEN to be set.")

    # Consider stronger session protection if using HTTPS
    # SESSION_COOKIE_SECURE = True
    # SESSION_COOKIE_HTTPONLY = True
    # SESSION_COOKIE_SAMESITE = 'Lax' # Or 'Strict'
    # REMEMBER_COOKIE_SECURE = True
    # REMEMBER_COOKIE_HTTPONLY = True

    @classmethod
    def init_app(cls, app):
        """Initialize production-specific settings."""
        Config.init_app(app) # Call base init_app if it exists

        # --- Production Logging Setup ---
        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        log_dir = os.path.join(basedir, 'logs') # Assumes logs dir in project root

        try:
            # Ensure log directory exists
            os.makedirs(log_dir, exist_ok=True)

            # Configure file handler
            log_file = os.path.join(log_dir, 'cfap_app.log')
            # Rotate logs at 10MB, keep 5 backups
            file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
            # Consistent log format
            log_format = logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            )
            file_handler.setFormatter(log_format)

            # Set log level for the file handler and app logger
            log_level_numeric = getattr(logging, log_level, logging.INFO)
            file_handler.setLevel(log_level_numeric)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(log_level_numeric)

            # Remove default Flask handler if you want file-only logging in prod
            # Or keep it if you want logs to go to console/stderr as well (e.g., via systemd journal)
            # del app.logger.handlers[0] # Uncomment to remove default handler

            app.logger.info(f'CapConduit CFAP startup in production mode. Log Level: {log_level}')

        except Exception as e:
            app.logger.error(f"Failed to configure file logging: {e}", exc_info=True)
            # Fallback or raise error


# Dictionary to access configuration classes by name
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig # Default to development if FLASK_ENV not set/invalid
}