import os
import logging
from flask import Flask, render_template, redirect, url_for, flash, jsonify, session, request, make_response
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import click
from datetime import datetime, timedelta
import urllib.parse
import sqlalchemy as sa
import gzip
from io import BytesIO
import functools

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

# List of keys to exclude from session storage (to reduce size)
app.config['SESSION_EXCLUDE_KEYS'] = ['large_data', 'temp_data', '_csrf_token']

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

# Apply decorators in correct order - cache headers first, then compression
# Add browser caching headers for static content
@app.after_request
def add_cache_headers(response):
    # Only add cache headers to successful responses
    if not hasattr(response, 'status_code'):
        return response
        
    if response.status_code < 400:
        # Static files (CSS, JS, images)
        if request.path.startswith('/static/'):
            # Cache for 1 week
            response.headers['Cache-Control'] = 'public, max-age=604800'
        elif request.path.startswith('/assets/'):
            # Cache for 1 day
            response.headers['Cache-Control'] = 'public, max-age=86400'
        else:
            # Default to no-cache for dynamic content
            if 'Cache-Control' not in response.headers:
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    
    # Add additional performance headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    return response

# Apply gzip compression to all responses
@app.after_request
def apply_gzip_compression(response):
    # Guard against ClosingIterator responses that don't have status_code
    if not hasattr(response, 'status_code'):
        return response
        
    # Don't compress small responses or already compressed responses
    if (response.status_code != 200 or
            len(response.get_data()) < 500 or  # Less than 500 bytes
            'Content-Encoding' in response.headers or
            not response.headers.get('Content-Type', '').startswith(('text/', 'application/json', 'application/javascript'))):
        return response
        
    # Check if client accepts gzip encoding
    if 'gzip' not in request.headers.get('Accept-Encoding', ''):
        return response
        
    # Compress the response
    gzip_buffer = BytesIO()
    with gzip.GzipFile(mode='wb', fileobj=gzip_buffer) as gzip_file:
        gzip_file.write(response.get_data())
    
    # Update response with compressed data
    response.set_data(gzip_buffer.getvalue())
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(response.get_data())
    response.headers['Vary'] = 'Accept-Encoding'
    
    return response

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