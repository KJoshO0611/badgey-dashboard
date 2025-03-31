"""
Custom Session Interface for Flask-Session that works with our existing dashboard_sessions schema.
"""

import pickle
import sqlalchemy as sa
import redis
import logging
from base64 import b64encode, b64decode
from datetime import datetime, timedelta
from flask.sessions import SessionInterface, SessionMixin
from flask import request, current_app
from werkzeug.datastructures import CallbackDict
from flask_login import current_user
from uuid import uuid4
from itsdangerous.url_safe import URLSafeSerializer

# Create a standard logger instead of using current_app.logger
logger = logging.getLogger(__name__)

class CustomSqlAlchemySession(CallbackDict, SessionMixin):
    """Custom session class that works with our dashboard_sessions table schema."""
    
    def __init__(self, initial=None, sid=None, permanent=None):
        def on_update(self):
            self.modified = True
            
        CallbackDict.__init__(self, initial, on_update)
        self.sid = sid
        if permanent:
            self.permanent = permanent
        self.modified = False

class CustomSqlAlchemySessionInterface(SessionInterface):
    """Session interface that connects to our dashboard_sessions table."""
    
    serializer = pickle
    session_class = CustomSqlAlchemySession
    
    def __init__(self, db, table=None, key_prefix='session:', use_signer=False, redis_host=None, redis_port=6379, redis_password=None, redis_db=0):
        """Initialize the session interface.
        
        Args:
            db: SQLAlchemy db instance
            table: If None, will use our custom table definition matching the database schema
            key_prefix: Prefix for session keys
            use_signer: Whether to sign the session id
            redis_host: Redis host for caching
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis DB number
        """
        if db is None:
            raise ValueError('db argument is required')
            
        self.db = db
        self.key_prefix = key_prefix
        self.use_signer = use_signer
        
        # Store Redis connection parameters for later initialization
        self.redis = None
        self.redis_params = {
            'host': redis_host,
            'port': redis_port,
            'password': redis_password,
            'db': redis_db,
            'socket_timeout': 1,
            'socket_connect_timeout': 1
        }
        
        # Define the session model to match our schema
        class SessionModel(object):
            """Model for the dashboard_sessions table."""
            __tablename__ = 'dashboard_sessions'
            
            id = sa.Column(sa.String(128), primary_key=True)
            user_id = sa.Column(sa.Integer, nullable=False)
            data = sa.Column(sa.Text)
            created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
            expires_at = sa.Column(sa.DateTime)
            
        # Create the table metadata
        metadata = sa.MetaData()
        self.table = sa.Table(
            'dashboard_sessions',
            metadata,
            sa.Column('id', sa.String(128), primary_key=True),
            sa.Column('user_id', sa.Integer, nullable=False),
            sa.Column('data', sa.Text),
            sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
            sa.Column('expires_at', sa.DateTime)
        )
        
        # Map the model to the table
        if table is None:
            pass  # Using our custom table definition above
        else:
            self.table = table
            
        # Create the session model class
        self.session_model = type('CustomSessionModel', (SessionModel,), {})
    
    def _get_redis(self):
        """Lazily initialize Redis connection only when needed and within app context."""
        if self.redis is not None:
            return self.redis
        
        # Only initialize if host is provided
        if not self.redis_params['host']:
            return None
            
        try:
            self.redis = redis.Redis(**self.redis_params)
            # Test the connection
            self.redis.ping()
            logger.info("Redis cache connection established")
            return self.redis
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.redis = None
            return None
        
    def open_session(self, app, request):
        """Open a session from the request."""
        cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
        sid = request.cookies.get(cookie_name)
        
        app.logger.debug(f"Opening session with cookie name: {cookie_name}, sid exists: {sid is not None}")
        
        if not sid:
            # No session ID, create a new session
            new_sid = self._generate_sid()
            app.logger.debug(f"No session ID found, creating new session: {new_sid}")
            return self.session_class(sid=new_sid, permanent=True)
        
        if self.use_signer:
            try:
                from itsdangerous import BadSignature
                from itsdangerous.url_safe import URLSafeSerializer
                signer = URLSafeSerializer(app.secret_key)
                sid = signer.loads(sid)
            except BadSignature:
                new_sid = self._generate_sid()
                app.logger.debug(f"Bad signature, creating new session: {new_sid}")
                return self.session_class(sid=new_sid, permanent=True)
            except Exception as e:
                app.logger.error(f"Error checking session signature: {e}")
                new_sid = self._generate_sid()
                return self.session_class(sid=new_sid, permanent=True)
        
        # Try to get session from Redis cache first
        redis_client = self._get_redis()
        if redis_client:
            try:
                cached_data = redis_client.get(f"session:{sid}")
                if cached_data:
                    app.logger.debug(f"Session found in Redis cache: {sid}")
                    session_data = self.serializer.loads(cached_data)
                    return self.session_class(session_data, sid=sid, permanent=True)
            except Exception as e:
                app.logger.error(f"Error fetching session from Redis: {e}")
        
        # If not in Redis or Redis is not available, try the database
        try:
            conn = self.db.connect()
            result = conn.execute(
                sa.select(self.table.c.data)
                .where(self.table.c.id == sid)
                .where(self.table.c.expires_at > datetime.utcnow())
            ).fetchone()
            
            if result and result[0]:
                try:
                    data = b64decode(result[0])
                    session_data = self.serializer.loads(data)
                    app.logger.debug(f"Loaded existing session data for sid: {sid}")
                    
                    # Store in Redis cache for faster future access
                    redis_client = self._get_redis()
                    if redis_client:
                        try:
                            # Calculate TTL based on session expiration
                            ttl = app.config.get('PERMANENT_SESSION_LIFETIME', timedelta(days=7)).total_seconds()
                            redis_client.setex(
                                f"session:{sid}", 
                                int(ttl), 
                                self.serializer.dumps(session_data)
                            )
                            app.logger.debug(f"Session cached in Redis: {sid}")
                        except Exception as e:
                            app.logger.error(f"Error caching session in Redis: {e}")
                    
                    return self.session_class(session_data, sid=sid, permanent=True)
                except Exception as e:
                    app.logger.error(f"Error deserializing session data: {e}")
            
        except Exception as e:
            app.logger.error(f"Error loading session from database: {e}")
        
        # If we get here, either the session doesn't exist or is expired
        new_sid = self._generate_sid()
        app.logger.debug(f"Creating new session due to load failure: {new_sid}")
        return self.session_class(sid=new_sid, permanent=True)
    
    def save_session(self, app, session, response):
        """Save the session to the database."""
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
        
        if not hasattr(response, 'set_cookie'):
            app.logger.error(f"Response object doesn't have set_cookie method. Type: {type(response)}")
            return
        
        # Don't save empty sessions
        if not session:
            if session.modified:
                self._delete_session(session.sid)
                response.delete_cookie(cookie_name, domain=domain, path=path)
            return
        
        # Only save if modified
        if not session.modified:
            return
            
        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)
        samesite = self.get_cookie_samesite(app)
        expires = self.get_expiration_time(app, session)
        
        sid = session.sid if session.sid else self._generate_sid()
        
        # Get current user ID
        user_id = getattr(current_user, 'id', 1)
        
        # Prepare session data
        session_data = dict(session)
        
        # Remove any excluded keys
        exclude_keys = app.config.get('SESSION_EXCLUDE_KEYS', [])
        for key in exclude_keys:
            session_data.pop(key, None)
        
        # Ensure we're not storing empty data
        if not session_data:
            session_data['_created'] = datetime.utcnow().isoformat()
        
        try:
            # Serialize the data
            serialized = self.serializer.dumps(session_data)
            encoded_data = b64encode(serialized).decode('utf-8')
            
            # Save to database
            conn = self.db.connect()
            trans = conn.begin()
            
            try:
                # Upsert the session
                stmt = sa.text("""
                    INSERT INTO dashboard_sessions (id, user_id, data, created_at, expires_at)
                    VALUES (:sid, :user_id, :data, :created_at, :expires_at)
                    ON DUPLICATE KEY UPDATE
                        user_id = VALUES(user_id),
                        data = VALUES(data),
                        expires_at = VALUES(expires_at)
                """)
                
                conn.execute(
                    stmt,
                    {
                        'sid': sid,
                        'user_id': user_id,
                        'data': encoded_data,
                        'created_at': datetime.utcnow(),
                        'expires_at': expires
                    }
                )
                
                trans.commit()
                app.logger.debug(f"Successfully saved session {sid} to database")
                
                # Also update the Redis cache
                redis_client = self._get_redis()
                if redis_client:
                    try:
                        # Calculate TTL based on session expiration
                        ttl = app.config.get('PERMANENT_SESSION_LIFETIME', timedelta(days=7)).total_seconds()
                        redis_client.setex(
                            f"session:{sid}", 
                            int(ttl), 
                            serialized  # Use the non-base64 serialized data for Redis
                        )
                        app.logger.debug(f"Session updated in Redis cache: {sid}")
                    except Exception as e:
                        app.logger.error(f"Error updating session in Redis: {e}")
                
            except Exception as e:
                trans.rollback()
                app.logger.error(f"Error saving session to database: {e}")
                raise
                
        except Exception as e:
            app.logger.error(f"Error in save_session: {e}")
            return
            
        # Set the cookie
        if self.use_signer:
            signer = URLSafeSerializer(app.secret_key)
            sid = signer.dumps(sid)
            
        response.set_cookie(
            cookie_name,
            sid,
            expires=expires,
            httponly=httponly,
            domain=domain,
            path=path,
            secure=secure,
            samesite=samesite
        )
    
    def _generate_sid(self):
        """Generate a unique session ID."""
        return str(uuid4())
        
    def _delete_session(self, sid):
        """Delete a session from the database and Redis."""
        try:
            # Delete from database
            conn = self.db.connect()
            trans = conn.begin()  # Start a transaction explicitly
            
            try:
                conn.execute(self.table.delete().where(self.table.c.id == sid))
                trans.commit()  # Commit the delete transaction
                logger.debug(f"Deleted session from DB: {sid}")
                
                # Also delete from Redis if available
                redis_client = self._get_redis()
                if redis_client:
                    try:
                        redis_client.delete(f"session:{sid}")
                        logger.debug(f"Deleted session from Redis: {sid}")
                    except Exception as e:
                        logger.error(f"Error deleting session from Redis: {e}")
                
            except Exception as e:
                trans.rollback()  # Rollback on error
                logger.error(f"Error deleting session from DB, rolled back: {e}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error deleting session: {e}")

# New class for lazy loading session data
class LazyLoadingSession(CustomSqlAlchemySession):
    """Session class that only loads data from the database when accessed."""
    
    def __init__(self, sid, session_interface, app, permanent=None):
        self.sid = sid
        self.session_interface = session_interface
        self.app = app
        self._loaded = False
        self._data = {}
        if permanent:
            self.permanent = permanent
        self.modified = False
        
    def _load(self):
        """Load session data from the database when needed."""
        if self._loaded:
            return
            
        try:
            # Load session data from database
            conn = self.session_interface.db.connect()
            trans = conn.begin()
            
            try:
                result = conn.execute(
                    sa.select(self.session_interface.table.c.data, self.session_interface.table.c.expires_at)
                    .where(self.session_interface.table.c.id == self.sid)
                ).fetchone()
                
                trans.commit()
                
                if result and result.data:
                    data, expires = result
                    
                    # Check if the session has expired
                    if expires is not None and expires < datetime.utcnow():
                        self.app.logger.debug(f"Session expired: {self.sid}")
                        # Just use empty session data
                        self._data = {}
                    else:
                        # Load the data
                        try:
                            decoded_data = b64decode(data.encode('utf-8'))
                            session_data = self.session_interface.serializer.loads(decoded_data)
                            self._data = session_data
                            self.app.logger.debug(f"Successfully loaded session data for sid: {self.sid}")
                        except Exception as e:
                            self.app.logger.error(f"Error deserializing session data: {e}")
                            self._data = {}
                else:
                    self._data = {}
            except Exception as e:
                # Rollback the transaction in case of error
                trans.rollback()
                self.app.logger.error(f"Database error while reading session: {e}")
                self._data = {}
            finally:
                conn.close()
        except Exception as e:
            # Log the error and create a new session
            self.app.logger.error(f"Error loading session: {e}")
            self._data = {}
            
        self._loaded = True
        
    def __getitem__(self, key):
        self._load()
        return self._data.get(key)
        
    def __setitem__(self, key, value):
        self._load()
        self._data[key] = value
        self.modified = True
        
    def __delitem__(self, key):
        self._load()
        if key in self._data:
            del self._data[key]
            self.modified = True
            
    def __iter__(self):
        self._load()
        return iter(self._data)
        
    def __len__(self):
        self._load()
        return len(self._data)
        
    def __contains__(self, key):
        self._load()
        return key in self._data
        
    def get(self, key, default=None):
        self._load()
        return self._data.get(key, default)
        
    def pop(self, key, default=None):
        self._load()
        self.modified = True
        return self._data.pop(key, default)
        
    def clear(self):
        self._load()
        self._data.clear()
        self.modified = True 