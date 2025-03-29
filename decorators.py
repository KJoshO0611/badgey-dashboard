from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def role_required(roles):
    """
    Decorator for views that require specific role(s)
    
    Args:
        roles (list): List of required roles (any match grants access)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('auth.login'))
            
            # Check if user has any of the required roles or is admin
            if current_user.is_admin:
                return f(*args, **kwargs)
                
            if isinstance(roles, list):
                for role in roles:
                    if current_user.has_role(role):
                        return f(*args, **kwargs)
            else:
                if current_user.has_role(roles):
                    return f(*args, **kwargs)
            
            flash('You do not have permission to access this page', 'error')
            return redirect(url_for('index'))
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator for views that require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            flash('Admin privileges required to access this page', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function 