import os
import logging
from flask import Flask, render_template, redirect, url_for, flash, jsonify, session, request
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import click
from datetime import datetime, timedelta
import urllib.parse
import sqlalchemy as sa

# Load environment variables
load_dotenv()

# Import blueprints and models (to be created in separate files)
from routes.auth import auth_bp
from routes.quizzes import quizzes_bp
from routes.analytics import analytics_bp
from routes.admin import admin_bp
from routes.api import api_bp
from models.db import init_db, get_db
from models.user import User, init_user_table

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to stdout/stderr only
    ]
)
logger = logging.getLogger(__name__)

# Enable more verbose logging for Flask and SQLAlchemy
logging.getLogger('flask').setLevel(logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Create and configure the app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')
app.config['DATABASE'] = {
    'host': os.getenv('DBHOST', 'localhost'),
    'port': int(os.getenv('DBPORT', 3306)),
    'user': os.getenv('DBUSER', 'root'),
    'password': os.getenv('DBPASSWORD', ''),
    'database': os.getenv('DBNAME', 'badgey')
}

# Session configuration
# You have two options:

# Option 1: Use built-in cookie-based sessions (simpler, but doesn't use dashboard_sessions table)
#app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
#app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
#app.config['SESSION_COOKIE_HTTPONLY'] = True
#app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Option 2: Use custom database sessions that work with your dashboard_sessions schema
# Create SQLAlchemy engine for session storage
username = urllib.parse.quote_plus(app.config['DATABASE']['user'])
password = urllib.parse.quote_plus(app.config['DATABASE']['password'])
host = app.config['DATABASE']['host']
port = app.config['DATABASE']['port']
database = app.config['DATABASE']['database']
engine_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"

# Configure session settings
app.config['SESSION_COOKIE_NAME'] = 'session'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Create the database engine (without models, just for raw SQL)
db = sa.create_engine(engine_url)

# Import and use our custom session interface
from custom_session import CustomSqlAlchemySessionInterface
app.session_interface = CustomSqlAlchemySessionInterface(db=db)

app.config['DISCORD_CLIENT_ID'] = os.getenv('DISCORD_CLIENT_ID')
app.config['DISCORD_CLIENT_SECRET'] = os.getenv('DISCORD_CLIENT_SECRET')
app.config['DISCORD_REDIRECT_URI'] = os.getenv('DISCORD_REDIRECT_URI')

# For handling proxy headers
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Add Jinja filters
@app.template_filter('datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    """Format a datetime object."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    return value.strftime(format)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(quizzes_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp, url_prefix='/api')

@login_manager.user_loader
def load_user(user_id):
    """Load the user from the database."""
    return User.get_by_id(int(user_id))

@app.route('/')
def index():
    """Render the homepage."""
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page."""
    # Mock data for the dashboard - in a real implementation, these would be fetched from the database
    user_stats = {
        'quiz_count': 0,
        'recent_score': 'N/A',
        'question_count': 0,
        'quizzes_taken': 0
    }
    
    recent_activity = []
    user_quizzes = []
    
    return render_template(
        'dashboard.html',
        user_stats=user_stats,
        recent_activity=recent_activity,
        user_quizzes=user_quizzes
    )

@app.route('/health')
def health_check():
    """Health check endpoint for Docker."""
    return jsonify(status="healthy"), 200

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {e}")
    return render_template('errors/500.html'), 500

@app.cli.command('init-db')
def init_db_command():
    """Initialize the database tables."""
    init_db()
    init_user_table()
    click.echo('Initialized the database.')

if __name__ == '__main__':
    # Use PORT environment variable if provided by hosting platform
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 