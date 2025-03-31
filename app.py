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
from flask_session import Session
# Only import extensions that are actually used
# from flask_caching import Cache  
from flask_compress import Compress
from flask_wtf.csrf import CSRFProtect
from models.db import get_db, init_db
from models.user import User, init_user_table
from routes.auth import auth_bp
from routes.quizzes import quizzes_bp
from routes.analytics import analytics_bp
from routes.admin import admin_bp
from routes.api import api_bp

# Load environment variables
load_dotenv()

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
    # Only add cache headers if response has a status_code attribute
    if not hasattr(response, 'status_code'):
        return response
        
    # Apply caching to successful responses
    if response.status_code < 400:
        # Special handling for static files
        if request.path.startswith('/static/'):
            # Cache for 1 week
            response.headers['Cache-Control'] = 'public, max-age=604800'
            # Don't try to modify these responses further
            return response
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

# Apply gzip compression to all responses - but skip static files
@app.after_request
def apply_gzip_compression(response):
    # Skip compression for static files completely
    if request.path.startswith(('/static/', '/assets/')):
        return response
        
    # Guard against ClosingIterator responses that don't have status_code
    if not hasattr(response, 'status_code'):
        return response
    
    # Don't try to compress responses in direct passthrough mode
    if hasattr(response, 'direct_passthrough') and response.direct_passthrough:
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
        
    try:
        # Compress the response
        gzip_buffer = BytesIO()
        with gzip.GzipFile(mode='wb', fileobj=gzip_buffer) as gzip_file:
            gzip_file.write(response.get_data())
        
        # Update response with compressed data
        response.set_data(gzip_buffer.getvalue())
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = len(response.get_data())
        response.headers['Vary'] = 'Accept-Encoding'
    except Exception as e:
        # If compression fails for any reason, log it and return the original response
        app.logger.error(f"Error compressing response: {e}")
    
    return response

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Initialize database
with app.app_context():
    init_db()
    logger.info("Database initialized")

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
    # Fetch real data for the dashboard
    user_stats = {
        'quiz_count': 0,
        'recent_score': 'N/A',
        'question_count': 0,
        'quizzes_taken': 0
    }
    
    recent_activity = []
    user_quizzes = []
    
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Count quizzes created by user
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM quizzes 
                WHERE creator_id = %s
            """, (current_user.discord_id,))
            user_stats['quiz_count'] = cursor.fetchone()['count']
            
            # Count questions created by user
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM questions q
                JOIN quizzes qz ON q.quiz_id = qz.quiz_id
                WHERE qz.creator_id = %s
            """, (current_user.discord_id,))
            user_stats['question_count'] = cursor.fetchone()['count']
            
            # Count quizzes taken by user
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM user_scores 
                WHERE user_id = %s
            """, (current_user.discord_id,))
            user_stats['quizzes_taken'] = cursor.fetchone()['count']
            
            # Get most recent score
            cursor.execute("""
                SELECT score 
                FROM user_scores 
                WHERE user_id = %s 
                ORDER BY completion_date DESC 
                LIMIT 1
            """, (current_user.discord_id,))
            recent_score = cursor.fetchone()
            if recent_score:
                user_stats['recent_score'] = f"{recent_score['score']}%"
            
            # Get recent activity
            cursor.execute("""
                SELECT us.*, q.quiz_name, q.quiz_id
                FROM user_scores us
                JOIN quizzes q ON us.quiz_id = q.quiz_id
                WHERE us.user_id = %s
                ORDER BY us.completion_date DESC
                LIMIT 5
            """, (current_user.discord_id,))
            activity_data = cursor.fetchall()
            
            for item in activity_data:
                action = "Completed Quiz"
                recent_activity.append({
                    'action': action,
                    'description': f"Scored {item['score']}% on {item['quiz_name']}",
                    'timestamp': item['completion_date'].strftime('%Y-%m-%d %H:%M')
                })
            
            # Get user's quizzes
            cursor.execute("""
                SELECT q.quiz_id as id, q.quiz_name as name, q.creation_date,
                       COUNT(DISTINCT qu.question_id) as question_count,
                       COUNT(DISTINCT us.id) as completion_count
                FROM quizzes q
                LEFT JOIN questions qu ON q.quiz_id = qu.quiz_id
                LEFT JOIN user_scores us ON q.quiz_id = us.quiz_id
                WHERE q.creator_id = %s
                GROUP BY q.quiz_id, q.quiz_name, q.creation_date
                ORDER BY q.creation_date DESC
                LIMIT 5
            """, (current_user.discord_id,))
            user_quizzes = cursor.fetchall()
            
            # Format creation_date dates
            for quiz in user_quizzes:
                if 'creation_date' in quiz and quiz['creation_date']:
                    quiz['created_at'] = quiz['creation_date'].strftime('%Y-%m-%d')
                else:
                    quiz['created_at'] = 'N/A'
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
    
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
    """Clear the existing data and create new tables."""
    with app.app_context():
        init_db()
    click.echo('Initialized the database.')

if __name__ == '__main__':
    # Use PORT environment variable if provided by hosting platform
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 