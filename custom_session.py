"""
Custom Session Interface for Flask-Session that works with our existing dashboard_sessions schema.
"""

import pickle
import sqlalchemy as sa
from base64 import b64encode, b64decode
from datetime import datetime
from flask.sessions import SessionInterface, SessionMixin
from flask import request, current_app
from werkzeug.datastructures import CallbackDict
from flask_login import current_user
from uuid import uuid4

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
    
    def __init__(self, db, table=None, key_prefix='session:', use_signer=False):
        """Initialize the session interface.
        
        Args:
            db: SQLAlchemy db instance
            table: If None, will use our custom table definition matching the database schema
            key_prefix: Prefix for session keys
            use_signer: Whether to sign the session id
        """
        if db is None:
            raise ValueError('db argument is required')
            
        self.db = db
        self.key_prefix = key_prefix
        self.use_signer = use_signer
        
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
        
    def open_session(self, app, request):
        """Open a session from the request."""
        sid = request.cookies.get(app.session_cookie_name)
        if not sid:
            # No session ID, create a new session
            return self.session_class(sid=self._generate_sid(), permanent=True)
        
        if self.use_signer:
            # Sign the session ID if configured
            try:
                from itsdangerous import BadSignature
                from itsdangerous.url_safe import URLSafeSerializer
                signer = URLSafeSerializer(app.secret_key)
                sid = signer.loads(sid)
            except BadSignature:
                # Invalid signature, create a new session
                return self.session_class(sid=self._generate_sid(), permanent=True)
        
        # Remove the prefix from the session ID
        if self.key_prefix:
            sid = sid[len(self.key_prefix):]
        
        # Look up the session in the database
        try:
            # Use raw SQL to avoid SQLAlchemy model issues
            conn = self.db.engine.connect()
            result = conn.execute(
                sa.select([self.table.c.data, self.table.c.expires_at])
                .where(self.table.c.id == sid)
            ).fetchone()
            conn.close()
            
            if result is None:
                # No session found, create a new one
                return self.session_class(sid=self._generate_sid(), permanent=True)
                
            data, expires = result
            
            # Check if the session has expired
            if expires is not None and expires < datetime.utcnow():
                # Delete the expired session
                conn = self.db.engine.connect()
                conn.execute(self.table.delete().where(self.table.c.id == sid))
                conn.close()
                return self.session_class(sid=self._generate_sid(), permanent=True)
                
            # Load the data
            data = b64decode(data.encode('utf-8'))
            session_data = self.serializer.loads(data)
            return self.session_class(session_data, sid=sid, permanent=True)
        except Exception as e:
            # Log the error and create a new session
            app.logger.error(f"Error loading session: {e}")
            return self.session_class(sid=self._generate_sid(), permanent=True)
    
    def save_session(self, app, session, response):
        """Save the session to the database."""
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        
        # If the session is empty, delete it
        if not session:
            if session.modified:
                self._delete_session(session.sid)
                response.delete_cookie(app.session_cookie_name, domain=domain, path=path)
            return
        
        # Determine when the session should expire
        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)
        samesite = self.get_cookie_samesite(app)
        expires = self.get_expiration_time(app, session)
        
        # If the session ID doesn't exist, generate a new one
        sid = session.sid
        if not sid:
            sid = self._generate_sid()
            session.sid = sid
            
        # Get the user ID
        user_id = current_user.id if current_user.is_authenticated else 1  # Default to guest user ID
        
        # Serialize the session data
        serialized_data = self.serializer.dumps(dict(session))
        data = b64encode(serialized_data).decode('utf-8')
        
        # Save the session to the database
        try:
            conn = self.db.engine.connect()
            
            # Check if the session already exists
            result = conn.execute(
                sa.select([self.table.c.id])
                .where(self.table.c.id == sid)
            ).fetchone()
            
            if result is None:
                # Insert a new session
                conn.execute(
                    self.table.insert().values(
                        id=sid,
                        user_id=user_id,
                        data=data,
                        expires_at=expires
                    )
                )
            else:
                # Update the existing session
                conn.execute(
                    self.table.update()
                    .where(self.table.c.id == sid)
                    .values(
                        user_id=user_id,
                        data=data,
                        expires_at=expires
                    )
                )
            
            conn.close()
        except Exception as e:
            app.logger.error(f"Error saving session: {e}")
            
        # Set the session cookie
        if self.key_prefix:
            cookie_sid = self.key_prefix + sid
        else:
            cookie_sid = sid
            
        if self.use_signer:
            from itsdangerous.url_safe import URLSafeSerializer
            signer = URLSafeSerializer(app.secret_key)
            cookie_sid = signer.dumps(cookie_sid)
            
        response.set_cookie(
            app.session_cookie_name,
            cookie_sid,
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
        """Delete a session from the database."""
        try:
            conn = self.db.engine.connect()
            conn.execute(self.table.delete().where(self.table.c.id == sid))
            conn.close()
        except Exception as e:
            current_app.logger.error(f"Error deleting session: {e}") 