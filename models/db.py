import os
import pymysql
import logging
from flask import current_app, g

logger = logging.getLogger(__name__)

def get_db():
    """Get a database connection from the pool."""
    if 'db' not in g:
        try:
            g.db = pymysql.connect(
                host=current_app.config['DATABASE']['host'],
                port=current_app.config['DATABASE']['port'],
                user=current_app.config['DATABASE']['user'],
                password=current_app.config['DATABASE']['password'],
                database=current_app.config['DATABASE']['database'],
                cursorclass=pymysql.cursors.DictCursor,
                charset='utf8mb4'
            )
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise e
    return g.db

def close_db(e=None):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize the database tables if they don't exist."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # Create dashboard_users table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                discord_id VARCHAR(32) UNIQUE NOT NULL,
                username VARCHAR(128) NOT NULL,
                discriminator VARCHAR(4),
                avatar VARCHAR(128),
                email VARCHAR(255),
                roles TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            
            # Create dashboard_sessions table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_sessions (
                id VARCHAR(128) PRIMARY KEY,
                user_id INT NOT NULL,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES dashboard_users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            
            # Create dashboard_logs table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_logs (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT,
                action VARCHAR(64) NOT NULL,
                details TEXT,
                ip_address VARCHAR(45),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES dashboard_users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            
        conn.commit()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database tables: {e}")
        conn.rollback()
        raise e

def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)

def log_activity(user_id, action, details, ip_address=None):
    """
    Log user activity to dashboard_logs table
    
    Args:
        user_id (int): User ID
        action (str): Action performed (login, logout, etc.)
        details (str): Additional details about the action
        ip_address (str, optional): IP address of the user
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dashboard_logs (user_id, action, details, ip_address) 
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, action, details, ip_address)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")
        conn.rollback()
    finally:
        conn.close() 