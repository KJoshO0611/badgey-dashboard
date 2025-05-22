import os
import pymysql
import logging
from flask import current_app, g
import time
import threading

logger = logging.getLogger(__name__)

# Connection pool for better performance
_connection_pool = None
_pool_lock = threading.Lock()
MAX_POOL_SIZE = 10
IDLE_TIMEOUT = 300  # seconds
_last_used = {}

def _create_connection():
    """Create a new database connection."""
    try:
        conn = pymysql.connect(
            host=current_app.config['DATABASE']['host'],
            port=current_app.config['DATABASE']['port'],
            user=current_app.config['DATABASE']['user'],
            password=current_app.config['DATABASE']['password'],
            database=current_app.config['DATABASE']['database'],
            cursorclass=pymysql.cursors.DictCursor,
            charset='utf8mb4',
            connect_timeout=5
        )
        logger.debug("Created new database connection")
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise e

def _init_connection_pool():
    """Initialize the connection pool."""
    global _connection_pool
    with _pool_lock:
        if _connection_pool is None:
            _connection_pool = []

def get_db():
    """Get a database connection from the pool."""
    global _connection_pool
    
    # Initialize pool if not already done
    if _connection_pool is None:
        _init_connection_pool()
    
    # Check for connection in app context first (for request transactions)
    if 'db' in g:
        return g.db
    
    conn = None
    with _pool_lock:
        # Clean up idle connections periodically
        now = time.time()
        _connection_pool = [
            c for c in _connection_pool 
            if c.open and now - _last_used.get(id(c), 0) < IDLE_TIMEOUT
        ]
        
        # Get connection from pool or create new one
        if _connection_pool:
            conn = _connection_pool.pop()
            logger.debug("Reusing connection from pool")
            
            # Ping the connection to make sure it's still alive
            try:
                conn.ping(reconnect=True)
            except:
                logger.debug("Connection ping failed, creating new connection")
                conn = _create_connection()
        else:
            logger.debug("No connection in pool, creating new one")
            conn = _create_connection()
    
    # Update last used timestamp
    _last_used[id(conn)] = time.time()
    return conn

def release_db(conn):
    """Release a database connection back to the pool."""
    if conn is None:
        return
        
    global _connection_pool
    with _pool_lock:
        if conn.open and len(_connection_pool) < MAX_POOL_SIZE:
            _connection_pool.append(conn)
            _last_used[id(conn)] = time.time()
            logger.debug("Released connection back to pool")
        else:
            conn.close()
            logger.debug("Closed connection (pool full or connection closed)")

def close_db(e=None):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        release_db(db)

def close_all_connections():
    """Close all connections in the pool."""
    global _connection_pool
    with _pool_lock:
        for conn in _connection_pool:
            try:
                conn.close()
            except:
                pass
        _connection_pool = []
        _last_used.clear()
    logger.debug("Closed all database connections")

def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)
    app.before_first_request(_init_connection_pool)
    
    # Add connection pool cleanup on app shutdown
    if hasattr(app, 'teardown_appcontext'):
        @app.teardown_appcontext
        def shutdown_pool(exception=None):
            close_all_connections()
    
    # Migrate sessions on startup
    migrate_anonymous_sessions()

def migrate_anonymous_sessions():
    """Update any sessions with user_id=1 that should be anonymous to user_id=0."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # First check if the foreign key constraint exists and drop it if needed
            cursor.execute("""
                SELECT CONSTRAINT_NAME 
                FROM information_schema.KEY_COLUMN_USAGE 
                WHERE TABLE_NAME = 'dashboard_sessions' 
                  AND COLUMN_NAME = 'user_id' 
                  AND REFERENCED_TABLE_NAME = 'dashboard_users'
                  AND CONSTRAINT_SCHEMA = DATABASE()
            """)
            result = cursor.fetchone()
            
            if result and result.get('CONSTRAINT_NAME'):
                constraint_name = result['CONSTRAINT_NAME']
                logger.info(f"Found foreign key constraint: {constraint_name}")
                
                # Drop the constraint
                cursor.execute(f"""
                    ALTER TABLE dashboard_sessions
                    DROP FOREIGN KEY {constraint_name}
                """)
                logger.info(f"Successfully dropped foreign key constraint: {constraint_name}")
            
            # Check if user with ID 1 exists
            cursor.execute("SELECT id FROM dashboard_users WHERE id = 1")
            user_exists = cursor.fetchone() is not None
            
            if not user_exists:
                # Update all sessions with user_id=1 to user_id=0
                cursor.execute("""
                    UPDATE dashboard_sessions
                    SET user_id = 0
                    WHERE user_id = 1
                """)
                affected_rows = cursor.rowcount
                logger.info(f"Updated {affected_rows} anonymous sessions from user_id=1 to user_id=0")
                
        conn.commit()
        logger.info("Session migration completed successfully")
    except Exception as e:
        logger.error(f"Error during session migration: {e}")
        conn.rollback()
    finally:
        release_db(conn)

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
        release_db(conn)

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
                expires_at TIMESTAMP
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
    finally:
        release_db(conn) 