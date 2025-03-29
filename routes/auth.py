import os
import logging
import requests
import json
from flask import Blueprint, request, redirect, url_for, session, flash, render_template, current_app
from flask_login import login_user, logout_user, login_required, current_user
from requests_oauthlib import OAuth2Session
from models.user import User

# Set environment variable to allow OAuth2 over HTTP (for development only)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Discord OAuth2 constants
DISCORD_API_BASE_URL = 'https://discord.com/api/v10'
DISCORD_AUTHORIZATION_BASE_URL = f'{DISCORD_API_BASE_URL}/oauth2/authorize'
DISCORD_TOKEN_URL = f'{DISCORD_API_BASE_URL}/oauth2/token'
# Hardcoded redirect URI to ensure match with Discord Developer Portal
REDIRECT_URI = 'http://ec2-13-215-176-205.ap-southeast-1.compute.amazonaws.com/auth/callback'

def token_updater(token):
    """Update the session with the new token."""
    session['oauth2_token'] = token

def make_discord_session(token=None, state=None, scope=None):
    """Create a Discord OAuth2Session."""
    client_id = current_app.config['DISCORD_CLIENT_ID']
    # Use hardcoded redirect URI instead of from config
    redirect_uri = REDIRECT_URI
    
    if token:
        return OAuth2Session(client_id, token=token, auto_refresh_kwargs={
            'client_id': client_id,
            'client_secret': current_app.config['DISCORD_CLIENT_SECRET'],
        }, auto_refresh_url=DISCORD_TOKEN_URL, token_updater=token_updater)
    
    if not scope:
        scope = ['identify', 'email']
    
    return OAuth2Session(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state
    )

@auth_bp.route('/login')
def login():
    """Discord OAuth2 login route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Custom build the auth URL to match required pattern exactly
    client_id = current_app.config['DISCORD_CLIENT_ID']
    redirect_uri = REDIRECT_URI
    scope = 'email identify'
    state = os.urandom(16).hex()
    
    # Store state for CSRF protection
    session['oauth2_state'] = state
    
    # Build URL in exact order: base -> client_id -> response_type -> redirect -> scope
    authorization_url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={requests.utils.quote(redirect_uri)}"
        f"&scope={scope}"
        f"&state={state}"
    )
        
    return render_template('login.html', discord_oauth_url=authorization_url)

@auth_bp.route('/auth/callback')
def auth_callback():
    """Handle the Discord OAuth2 callback."""
    if 'error' in request.args:
        logger.error(f"Discord OAuth error: {request.args.get('error')}")
        flash(f"Error: {request.args.get('error')}", 'danger')
        return redirect(url_for('auth.login'))
    
    if 'state' not in request.args or 'oauth2_state' not in session:
        logger.error("Missing state parameter in OAuth callback")
        flash("Authentication error: Missing state parameter", 'warning')
        return redirect(url_for('auth.login'))
    
    if request.args.get('state') != session['oauth2_state']:
        logger.error("State mismatch in OAuth callback")
        flash("Authentication error: Invalid state parameter", 'warning')
        return redirect(url_for('auth.login'))
    
    # Get authorization code
    code = request.args.get('code')
    if not code:
        logger.error("No authorization code in callback")
        flash("Authentication error: No authorization code received", 'danger') 
        return redirect(url_for('auth.login'))
    
    # Exchange authorization code for access token
    try:
        # Manually exchange the code for a token
        token_data = {
            'client_id': current_app.config['DISCORD_CLIENT_ID'],
            'client_secret': current_app.config['DISCORD_CLIENT_SECRET'],
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI,
            'scope': 'identify email'
        }
        
        logger.info(f"Exchanging code for token with data: {token_data}")
        
        token_response = requests.post(DISCORD_TOKEN_URL, data=token_data)
        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.status_code} - {token_response.text}")
            flash("Failed to authenticate with Discord. Please try again.", 'danger')
            return redirect(url_for('auth.login'))
            
        token = token_response.json()
        session['oauth2_token'] = token
        
        logger.info(f"Successfully exchanged code for token")
    except Exception as e:
        logger.error(f"Error exchanging code for token: {str(e)}")
        flash("An error occurred during login. Please try again.", 'danger')
        return redirect(url_for('auth.login'))
    
    # Get the user info from Discord using the access token
    try:
        headers = {
            'Authorization': f"Bearer {token['access_token']}"
        }
        user_response = requests.get(f'{DISCORD_API_BASE_URL}/users/@me', headers=headers)
        
        if user_response.status_code != 200:
            logger.error(f"Failed to get user info: {user_response.status_code} - {user_response.text}")
            flash("Failed to get user information from Discord.", 'danger')
            return redirect(url_for('auth.login'))
            
        user_data = user_response.json()
        logger.info(f"Got user data: {user_data}")
        
        discord_id = user_data['id']
        username = user_data['username']
        discriminator = user_data.get('discriminator')
        avatar = user_data.get('avatar')
        email = user_data.get('email')
        
        # Check if this is the first user (make them admin)
        is_first_user = False
        try:
            from models.db import get_db
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM dashboard_users")
                result = cursor.fetchone()
                is_first_user = result['count'] == 0
                logger.info(f"First user check: {is_first_user}")
        except Exception as e:
            logger.error(f"Error checking if first user: {str(e)}")
        
        # Default roles based on being first user
        roles = ['admin'] if is_first_user else ['user']
        
        # Create or update the user in our database
        db_user = User.create_or_update(
            discord_id=discord_id,
            username=username,
            discriminator=discriminator,
            avatar=avatar,
            email=email,
            roles=roles
        )
        
        # Log in the user
        login_user(db_user)
        logger.info(f"User logged in: {username} ({discord_id})")
        
        next_url = session.pop('next', None)
        if next_url:
            return redirect(next_url)
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Error during Discord authentication: {str(e)}")
        flash("An error occurred during login. Please try again.", 'danger')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the user."""
    logout_user()
    flash("You have been logged out successfully.", 'success')
    return redirect(url_for('index'))

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page."""
    return render_template('profile.html') 