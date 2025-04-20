import os
from dotenv import load_dotenv

# Load base .env file
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '..', '.env') # Assumes .env is in the project root (cfap/)
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
     # Consider logging a warning if .env is not found
     print(f"Warning: .env file not found at {dotenv_path}")


class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string-default'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Add other base configurations here
    # e.g., MAIL_SERVER, MAIL_PORT, etc.

    # Security token for internal API calls from Asterisk
    INTERNAL_API_TOKEN = os.environ.get('INTERNAL_API_TOKEN') # Load from .env

    @staticmethod
    def init_app(app):
        # Perform app-specific initialization if needed
        pass

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') or \
        'postgresql://call_platform_user:Sudh%403299@localhost:5432/call_platform_db' # Example fallback
    # Add development-specific settings, e.g., enable debug toolbar
    # SQLALCHEMY_ECHO = True # Useful for debugging SQL queries

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SECRET_KEY = 'test-secret-key' # Use a fixed key for testing sessions
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URI') or \
        'postgresql://call_platform_user:Sudh%403299@localhost:5432/call_platform_test_db' # Use a separate test DB
    WTF_CSRF_ENABLED = False # Disable CSRF forms validation in tests

class ProductionConfig(Config):
    """Production configuration."""
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI')
    # Add production-specific settings:
    # - Configure logging to file/external service
    # - Ensure DEBUG is False
    # - Consider SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True if using HTTPS

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        # Production specific initialization, e.g., logging setup
        import logging
        from logging.handlers import RotatingFileHandler

        log_dir = os.path.join(basedir, '..', 'logs') # Assumes logs dir in project root
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(os.path.join(log_dir,'cfap_app.log'),
                                           maxBytes=102400, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('CapConduit CFAP startup in production mode')


# Dictionary to access configuration classes by name
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig # Default to development if FLASK_ENV not set
}