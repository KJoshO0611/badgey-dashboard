import os
import logging
import requests
import json
from flask import Blueprint, request, redirect, url_for, session, flash, render_template, current_app
from flask_login import login_user, logout_user, login_required, current_user
from requests_oauthlib import OAuth2Session
from models.user import User

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Discord OAuth2 constants
DISCORD_API_BASE_URL = 'https://discord.com/api/v10'
DISCORD_AUTHORIZATION_BASE_URL = f'{DISCORD_API_BASE_URL}/oauth2/authorize'
DISCORD_TOKEN_URL = f'{DISCORD_API_BASE_URL}/oauth2/token'

def token_updater(token):
    """Update the session with the new token."""
    session['oauth2_token'] = token

def make_discord_session(token=None, state=None, scope=None):
    """Create a Discord OAuth2Session."""
    client_id = current_app.config['DISCORD_CLIENT_ID']
    redirect_uri = current_app.config['DISCORD_REDIRECT_URI']
    
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
        
    return render_template('login.html')

@auth_bp.route('/auth/discord')
def auth_discord():
    """Start the Discord OAuth2 flow."""
    discord = make_discord_session(scope=['identify', 'email'])
    authorization_url, state = discord.authorization_url(DISCORD_AUTHORIZATION_BASE_URL)
    
    # State is used to prevent CSRF
    session['oauth2_state'] = state
    
    # Redirect user to Discord for authorization
    return redirect(authorization_url)

@auth_bp.route('/auth/callback')
def auth_callback():
    """Handle the Discord OAuth2 callback."""
    if 'error' in request.args:
        flash(f"Error: {request.args['error']}", 'danger')
        return redirect(url_for('auth.login'))
    
    if 'oauth2_state' not in session:
        flash("You need to authorize with Discord first!", 'warning')
        return redirect(url_for('auth.login'))
    
    # Get the OAuth token
    try:
        discord = make_discord_session(state=session['oauth2_state'])
        token = discord.fetch_token(
            DISCORD_TOKEN_URL,
            client_secret=current_app.config['DISCORD_CLIENT_SECRET'],
            authorization_response=request.url
        )
        session['oauth2_token'] = token
    except Exception as e:
        logger.error(f"Error fetching OAuth token: {e}")
        flash("An error occurred during login. Please try again.", 'danger')
        return redirect(url_for('auth.login'))
    
    # Get the user info from Discord
    try:
        discord = make_discord_session(token=token)
        user_response = discord.get(f'{DISCORD_API_BASE_URL}/users/@me')
        user_data = user_response.json()
        
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
        except Exception as e:
            logger.error(f"Error checking if first user: {e}")
        
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
        
        next_url = session.pop('next', None)
        if next_url:
            return redirect(next_url)
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Error during Discord authentication: {e}")
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