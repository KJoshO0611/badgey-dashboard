import json
import logging
from flask_login import UserMixin
from models.db import get_db

logger = logging.getLogger(__name__)

class User(UserMixin):
    """User model for Flask-Login."""
    
    def __init__(self, id, discord_id, username, discriminator=None, avatar=None, email=None, roles=None):
        self.id = id
        self.discord_id = discord_id
        self.username = username
        self.discriminator = discriminator
        self.avatar = avatar
        self.email = email
        self.roles = json.loads(roles) if roles else []
        
    @property
    def avatar_url(self):
        """Get the user's Discord avatar URL."""
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.discord_id}/{self.avatar}.png"
        return "https://cdn.discordapp.com/embed/avatars/0.png"  # Default avatar
    
    def has_role(self, role):
        """Check if the user has a specific role."""
        return role in self.roles or 'admin' in self.roles
    
    @staticmethod
    def get_by_id(user_id):
        """Get a user by their ID."""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM dashboard_users WHERE id = %s",
                    (user_id,)
                )
                user_data = cursor.fetchone()
                if user_data:
                    return User(
                        id=user_data['id'],
                        discord_id=user_data['discord_id'],
                        username=user_data['username'],
                        discriminator=user_data['discriminator'],
                        avatar=user_data['avatar'],
                        email=user_data['email'],
                        roles=user_data['roles']
                    )
                return None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
    
    @staticmethod
    def get_by_discord_id(discord_id):
        """Get a user by their Discord ID."""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM dashboard_users WHERE discord_id = %s",
                    (discord_id,)
                )
                user_data = cursor.fetchone()
                if user_data:
                    return User(
                        id=user_data['id'],
                        discord_id=user_data['discord_id'],
                        username=user_data['username'],
                        discriminator=user_data['discriminator'],
                        avatar=user_data['avatar'],
                        email=user_data['email'],
                        roles=user_data['roles']
                    )
                return None
        except Exception as e:
            logger.error(f"Error getting user by Discord ID: {e}")
            return None
    
    @staticmethod
    def create_or_update(discord_id, username, discriminator=None, avatar=None, email=None, roles=None):
        """Create a new user or update an existing one."""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                # Check if user exists
                cursor.execute(
                    "SELECT id, roles FROM dashboard_users WHERE discord_id = %s",
                    (discord_id,)
                )
                existing_user = cursor.fetchone()
                
                roles_json = json.dumps(roles) if roles else None
                
                if existing_user:
                    # Update existing user but preserve their roles
                    cursor.execute(
                        """
                        UPDATE dashboard_users
                        SET username = %s, discriminator = %s, avatar = %s, email = %s
                        WHERE discord_id = %s
                        """,
                        (username, discriminator, avatar, email, discord_id)
                    )
                    user_id = existing_user['id']
                    
                    # Only set roles if this is a new user (don't overwrite existing roles on login)
                    if roles and not existing_user['roles']:
                        cursor.execute(
                            "UPDATE dashboard_users SET roles = %s WHERE discord_id = %s",
                            (roles_json, discord_id)
                        )
                else:
                    # Create new user
                    cursor.execute(
                        """
                        INSERT INTO dashboard_users 
                        (discord_id, username, discriminator, avatar, email, roles)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (discord_id, username, discriminator, avatar, email, roles_json)
                    )
                    user_id = cursor.lastrowid
                
                conn.commit()
                return User.get_by_id(user_id)
        except Exception as e:
            logger.error(f"Error creating/updating user: {e}")
            conn.rollback()
            raise e

def init_user_table():
    """Initialize the user table with an admin user if it doesn't exist."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # Check if there are any users
            cursor.execute("SELECT COUNT(*) as count FROM dashboard_users")
            result = cursor.fetchone()
            
            # If no users exist, create an admin user placeholder
            if result['count'] == 0:
                logger.info("No users found. You will need to login with Discord to create the first admin user.")
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error initializing user table: {e}")
        conn.rollback()
        raise e 