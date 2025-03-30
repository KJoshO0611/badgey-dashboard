import logging
import json
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify, send_file
from flask_login import login_required, current_user
from models.db import get_db
from models.user import User
from decorators import admin_required
import os
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Admin dashboard overview."""
    if not current_user.has_role('admin'):
        return render_template('errors/403.html'), 403
        
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get user count
            cursor.execute("SELECT COUNT(*) as count FROM dashboard_users")
            user_count = cursor.fetchone()['count']
            
            # Get quiz count
            cursor.execute("SELECT COUNT(*) as count FROM quizzes")
            quiz_count = cursor.fetchone()['count']
            
            # Get question count
            cursor.execute("SELECT COUNT(*) as count FROM questions")
            question_count = cursor.fetchone()['count']
            
            # Get score count
            cursor.execute("SELECT COUNT(*) as count FROM quiz_scores")
            score_count = cursor.fetchone()['count']
            
            # Get recent users
            cursor.execute("""
                SELECT *
                FROM dashboard_users
                ORDER BY last_login DESC
                LIMIT 5
            """)
            recent_users = cursor.fetchall()
            
            # Parse roles for each user
            for user in recent_users:
                if user['roles']:
                    user['roles_list'] = json.loads(user['roles'])
                else:
                    user['roles_list'] = []
            
            # Get recent dashboard logs
            cursor.execute("""
                SELECT l.*, u.username
                FROM dashboard_logs l
                LEFT JOIN dashboard_users u ON l.user_id = u.id
                ORDER BY l.timestamp DESC
                LIMIT 10
            """)
            recent_logs = cursor.fetchall()
            
        return render_template(
            'admin/dashboard.html',
            user_count=user_count,
            quiz_count=quiz_count,
            question_count=question_count,
            score_count=score_count,
            recent_users=recent_users,
            recent_logs=recent_logs
        )
    except Exception as e:
        logger.error(f"Error retrieving admin dashboard data: {e}")
        return render_template('errors/500.html'), 500

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """List all users."""
    if not current_user.has_role('admin'):
        return render_template('errors/403.html'), 403
        
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM dashboard_users
                ORDER BY created_at DESC
            """)
            users = cursor.fetchall()
            
            # Parse roles for each user
            for user in users:
                if user['roles']:
                    user['roles_list'] = json.loads(user['roles'])
                else:
                    user['roles_list'] = []
            
        return render_template('admin/users.html', users=users)
    except Exception as e:
        logger.error(f"Error retrieving users: {e}")
        return render_template('errors/500.html'), 500

@admin_bp.route('/users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit a user's roles."""
    if not current_user.has_role('admin'):
        return render_template('errors/403.html'), 403
        
    try:
        conn = get_db()
        
        if request.method == 'POST':
            # Get roles from form
            roles = request.form.getlist('roles')
            roles_json = json.dumps(roles)
            
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE dashboard_users SET roles = %s WHERE id = %s",
                    (roles_json, user_id)
                )
                conn.commit()
                
                # Log the action
                cursor.execute(
                    """
                    INSERT INTO dashboard_logs (user_id, action, details, ip_address)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        current_user.id,
                        "update_user_roles",
                        f"Updated roles for user ID {user_id}",
                        request.remote_addr
                    )
                )
                conn.commit()
                
            flash("User roles updated successfully!", "success")
            return redirect(url_for('admin.users'))
        
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM dashboard_users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for('admin.users'))
                
            # Parse roles
            if user['roles']:
                user['roles_list'] = json.loads(user['roles'])
            else:
                user['roles_list'] = []
                
            # Get available roles
            available_roles = [
                'admin',
                'user',
                'quiz_creator',
                'quiz_editor',
                'analytics'
            ]
            
        return render_template(
            'admin/edit_user.html',
            user=user,
            available_roles=available_roles
        )
    except Exception as e:
        logger.error(f"Error editing user: {e}")
        flash("An error occurred while editing the user.", "danger")
        return redirect(url_for('admin.users'))

@admin_bp.route('/delete_user', methods=['POST'])
@login_required
@admin_required
def delete_user():
    """Delete user"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID is required', 'error')
        return redirect(url_for('admin.users'))
    
    # Prevent self-deletion
    if int(user_id) == current_user.id:
        flash('You cannot delete your own account', 'error')
        return redirect(url_for('admin.users'))
    
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            query = "DELETE FROM dashboard_users WHERE id = %s"
            cursor.execute(query, (user_id,))
            conn.commit()
            
            flash('User deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting user: {e}', 'error')
        logger.error(f"Error deleting user: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/system')
@login_required
@admin_required
def system():
    """System settings"""
    return render_template('admin/system.html')

@admin_bp.route('/create_backup')
@login_required
@admin_required
def create_backup():
    """Create database backup"""
    try:
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}.sql"
        backup_path = os.path.join(current_app.root_path, 'backups', backup_filename)
        
        # Ensure backup directory exists
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        # Get database credentials from config
        db_config = current_app.config['DATABASE']
        
        # Build mysqldump command
        cmd = [
            'mysqldump',
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--user={db_config['user']}",
            f"--password={db_config['password']}",
            db_config['database']
        ]
        
        # Execute command and save output to file
        with open(backup_path, 'w') as f:
            subprocess.run(cmd, stdout=f, check=True)
        
        # Log the action
        logger.info(f"Database backup created: {backup_filename}")
        
        # Return the file for download
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/sql'
        )
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        flash(f"Error creating backup: {e}", "danger")
        return redirect(url_for('admin.system'))

@admin_bp.route('/restore_backup', methods=['POST'])
@login_required
@admin_required
def restore_backup():
    """Restore database from backup"""
    if 'backup_file' not in request.files:
        flash("No backup file provided", "danger")
        return redirect(url_for('admin.system'))
    
    backup_file = request.files['backup_file']
    
    if backup_file.filename == '':
        flash("No backup file selected", "danger")
        return redirect(url_for('admin.system'))
    
    try:
        # Create temporary file to store uploaded backup
        temp_backup_path = os.path.join(current_app.root_path, 'backups', 'temp_restore.sql')
        os.makedirs(os.path.dirname(temp_backup_path), exist_ok=True)
        backup_file.save(temp_backup_path)
        
        # Get database credentials from config
        db_config = current_app.config['DATABASE']
        
        # Build mysql command to restore
        cmd = [
            'mysql',
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--user={db_config['user']}",
            f"--password={db_config['password']}",
            db_config['database'],
            '-e', f"source {temp_backup_path}"
        ]
        
        # Execute command
        subprocess.run(cmd, check=True)
        
        # Clean up
        os.remove(temp_backup_path)
        
        # Log the action
        logger.info(f"Database restored from backup")
        flash("Database restored successfully", "success")
    except Exception as e:
        logger.error(f"Error restoring backup: {e}")
        flash(f"Error restoring backup: {e}", "danger")
    
    return redirect(url_for('admin.system'))

@admin_bp.route('/logs')
@login_required
@admin_required
def logs():
    """View system logs."""
    if not current_user.has_role('admin'):
        return render_template('errors/403.html'), 403
        
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT l.*, u.username
                FROM dashboard_logs l
                LEFT JOIN dashboard_users u ON l.user_id = u.id
                ORDER BY l.timestamp DESC
                LIMIT 100
            """)
            logs = cursor.fetchall()
            
        return render_template('admin/logs.html', logs=logs)
    except Exception as e:
        logger.error(f"Error retrieving logs: {e}")
        return render_template('errors/500.html'), 500

@admin_bp.route('/system-info')
@login_required
def system_info():
    """View system information."""
    if not current_user.has_role('admin'):
        return render_template('errors/403.html'), 403
        
    try:
        import platform
        import psutil
        import sys
        
        # Get system information
        system_info = {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'hostname': platform.node(),
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total,
            'memory_available': psutil.virtual_memory().available,
            'disk_usage': psutil.disk_usage('/'),
        }
        
        # Get database information
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() as version")
            db_version = cursor.fetchone()['version']
            
            cursor.execute("SHOW VARIABLES LIKE 'character_set_database'")
            charset = cursor.fetchone()['Value']
            
            # Get table sizes
            cursor.execute("""
                SELECT 
                    table_name, 
                    table_rows, 
                    data_length/1024/1024 as data_size_mb,
                    index_length/1024/1024 as index_size_mb
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                ORDER BY data_length DESC
            """)
            tables = cursor.fetchall()
            
        db_info = {
            'version': db_version,
            'charset': charset,
            'tables': tables
        }
        
        return render_template(
            'admin/system_info.html',
            system_info=system_info,
            db_info=db_info
        )
    except Exception as e:
        logger.error(f"Error retrieving system info: {e}")
        return render_template('errors/500.html'), 500

@admin_bp.route('/create_admin', methods=['GET', 'POST'])
@login_required
@admin_required
def create_admin():
    """Create a new admin user"""
    if request.method == 'POST':
        discord_id = request.form.get('discord_id')
        username = request.form.get('username')
        email = request.form.get('email')
        
        if not discord_id or not username:
            flash('Discord ID and username are required', 'error')
        else:
            # Check if user exists
            existing_user = User.get_by_discord_id(discord_id)
            
            if existing_user:
                # Update existing user to admin
                conn = get_db()
                cursor = conn.cursor()
                
                try:
                    # Get existing user's roles
                    query = "SELECT roles FROM dashboard_users WHERE discord_id = %s"
                    cursor.execute(query, (discord_id,))
                    user_data = cursor.fetchone()
                    
                    current_roles = json.loads(user_data['roles']) if user_data and user_data['roles'] else []
                    if 'admin' not in current_roles:
                        current_roles.append('admin')
                    
                    # Update user roles to include admin
                    query = "UPDATE dashboard_users SET roles = %s WHERE discord_id = %s"
                    cursor.execute(query, (json.dumps(current_roles), discord_id))
                    conn.commit()
                    
                    flash(f'User {username} updated to admin successfully', 'success')
                    return redirect(url_for('admin.users'))
                except Exception as e:
                    flash(f'Error updating user: {e}', 'error')
                finally:
                    cursor.close()
                    conn.close()
            else:
                # Create new admin user
                try:
                    user = User.create_or_update(
                        discord_id=discord_id, 
                        username=username, 
                        email=email, 
                        roles=['admin']
                    )
                    
                    if user:
                        flash(f'Admin user {username} created successfully', 'success')
                        return redirect(url_for('admin.users'))
                    else:
                        flash('Failed to create admin user', 'error')
                except Exception as e:
                    flash(f'Error creating admin user: {e}', 'error')
    
    return render_template('admin/create_admin.html')

@admin_bp.route('/api/user_roles')
@login_required
@admin_required
def api_user_roles():
    """API endpoint to get user roles"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            query = "SELECT id, discord_id, username, roles FROM dashboard_users"
            cursor.execute(query)
            users = cursor.fetchall()
            
            # Parse roles from JSON
            for user in users:
                user['roles'] = json.loads(user.get('roles', '[]'))
                # Add an is_admin property for the UI to use
                user['is_admin'] = 'admin' in user['roles']
            
            return jsonify(users)
    finally:
        conn.close()

@admin_bp.route('/api/update_user_roles', methods=['POST'])
@login_required
@admin_required
def update_user_roles():
    """Update user roles via API"""
    if not request.is_json:
        return jsonify({'error': 'Missing JSON data'}), 400
    
    data = request.json
    user_id = data.get('user_id')
    roles = data.get('roles', [])
    
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400
    
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Update user roles
            cursor.execute(
                "UPDATE dashboard_users SET roles = %s WHERE id = %s",
                (json.dumps(roles), user_id)
            )
            conn.commit()
            
            # Log the action
            cursor.execute(
                """
                INSERT INTO dashboard_logs (user_id, action, details, ip_address)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    current_user.id,
                    "update_user_roles",
                    f"Updated roles for user ID {user_id} via API",
                    request.remote_addr
                )
            )
            conn.commit()
            
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating user roles via API: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/update_user_roles', methods=['POST'])
@login_required
@admin_required
def update_user_roles():
    """Update user roles via web form"""
    user_id = request.form.get('user_id')
    roles = request.form.getlist('roles')
    
    if not user_id:
        flash('User ID is required', 'danger')
        return redirect(url_for('admin.users'))
    
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Update user roles
            cursor.execute(
                "UPDATE dashboard_users SET roles = %s WHERE id = %s",
                (json.dumps(roles), user_id)
            )
            conn.commit()
            
            # Log the action
            cursor.execute(
                """
                INSERT INTO dashboard_logs (user_id, action, details, ip_address)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    current_user.id,
                    "update_user_roles",
                    f"Updated roles for user ID {user_id}",
                    request.remote_addr
                )
            )
            conn.commit()
            
        flash("User roles updated successfully!", "success")
    except Exception as e:
        logger.error(f"Error updating user roles: {e}")
        flash(f"Error updating user roles: {e}", "danger")
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/update_settings', methods=['POST'])
@login_required
@admin_required
def update_settings():
    """Update system settings."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get form data
            site_title = request.form.get('site_title', 'Badgey Quiz Dashboard')
            maintenance_mode = 'maintenance_mode' in request.form
            allow_registration = 'allow_registration' in request.form
            
            # Check if settings exist
            cursor.execute("SELECT * FROM site_settings WHERE id = 1")
            if cursor.fetchone():
                # Update existing settings
                cursor.execute(
                    "UPDATE site_settings SET site_title = %s, maintenance_mode = %s, allow_registration = %s WHERE id = 1",
                    (site_title, maintenance_mode, allow_registration)
                )
            else:
                # Insert new settings
                cursor.execute(
                    "INSERT INTO site_settings (id, site_title, maintenance_mode, allow_registration) VALUES (1, %s, %s, %s)",
                    (site_title, maintenance_mode, allow_registration)
                )
                
            conn.commit()
            flash("Settings updated successfully!", "success")
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        flash(f"Error updating settings: {e}", "danger")
        
    return redirect(url_for('admin.system'))

@admin_bp.route('/clear_cache', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    """Clear application caches."""
    try:
        # Handle different cache types
        cache_data = 'cache_data' in request.form
        cache_session = 'cache_session' in request.form
        
        if cache_data:
            # Clear data cache logic here
            flash("Data cache cleared successfully!", "success")
            
        if cache_session:
            # Clear session data
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM dashboard_sessions")
                conn.commit()
            flash("Session cache cleared successfully! All users will be logged out.", "success")
            
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        flash(f"Error clearing cache: {e}", "danger")
        
    return redirect(url_for('admin.system')) 