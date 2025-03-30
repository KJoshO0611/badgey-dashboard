import logging
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from decorators import role_required
import json
from db_utils import get_db_connection
from datetime import datetime, timedelta
from models.db import get_db

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')

@analytics_bp.route('/')
@login_required
@role_required(['analytics_viewer', 'admin'])
def index():
    """Show the analytics dashboard"""
    # Get summary metrics
    metrics = get_summary_metrics()
    
    # Get top quizzes
    top_quizzes = get_top_quizzes(10)
    
    # Get recent activity
    recent_activity = get_recent_activity(10)
    
    # Get user stats
    user_stats = get_user_stats()
    
    return render_template(
        'analytics/index.html', 
        metrics=metrics,
        top_quizzes=top_quizzes,
        recent_activity=recent_activity,
        user_stats=user_stats
    )

@analytics_bp.route('/quizzes')
@login_required
@role_required(['analytics_viewer', 'admin'])
def quizzes():
    """Show quiz analytics"""
    conn = get_db()
    quiz_data = []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT q.quiz_id, q.quiz_name, 
                       q.user_name as creator, 
                       COUNT(DISTINCT us.id) as attempts, AVG(us.score) as avg_score,
                       COUNT(DISTINCT qu.question_id) as question_count
                FROM quizzes q
                LEFT JOIN user_scores us ON q.quiz_id = us.quiz_id
                LEFT JOIN questions qu ON q.quiz_id = qu.quiz_id
                GROUP BY q.quiz_id, q.quiz_name, q.user_name
                ORDER BY attempts DESC
            """)
            quiz_data = cursor.fetchall()
            
            # Format the data
            for quiz in quiz_data:
                if quiz['avg_score'] is not None:
                    quiz['avg_score'] = round(quiz['avg_score'], 1)
                else:
                    quiz['avg_score'] = 0
    except Exception as e:
        logger.error(f"Error fetching quiz analytics: {e}")
        
    return render_template('analytics/quizzes.html', quizzes=quiz_data)

@analytics_bp.route('/users')
@login_required
@role_required(['analytics_viewer', 'admin'])
def users():
    """Show user analytics"""
    conn = get_db()
    user_data = []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT us.user_id as discord_id, us.user_name as username, 
                       COUNT(us.id) as quizzes_taken,
                       AVG(us.score) as avg_score,
                       MAX(us.completion_date) as last_active
                FROM user_scores us
                GROUP BY us.user_id, us.user_name
                ORDER BY quizzes_taken DESC
            """)
            user_data = cursor.fetchall()
            
            # Format the data
            for user in user_data:
                if user['avg_score'] is not None:
                    user['avg_score'] = round(user['avg_score'], 1)
                else:
                    user['avg_score'] = 0
    except Exception as e:
        logger.error(f"Error fetching user analytics: {e}")
        
    return render_template('analytics/users.html', users=user_data)

@analytics_bp.route('/trends')
@login_required
@role_required(['analytics_viewer', 'admin'])
def trends():
    """Show trend analytics"""
    return render_template('analytics/trends.html')

# API endpoints for chart data
@analytics_bp.route('/api/summary')
@login_required
@role_required(['analytics_viewer', 'admin'])
def api_summary():
    """API endpoint for summary metrics"""
    metrics = get_summary_metrics()
    return jsonify(metrics)

@analytics_bp.route('/api/quiz_activity')
@login_required
@role_required(['analytics_viewer', 'admin'])
def api_quiz_activity():
    """API endpoint for quiz activity over time"""
    days = int(request.args.get('days', 30))
    activity = get_quiz_activity(days)
    return jsonify(activity)

@analytics_bp.route('/api/top_quizzes')
@login_required
@role_required(['analytics_viewer', 'admin'])
def api_top_quizzes():
    """API endpoint for top quizzes"""
    limit = int(request.args.get('limit', 10))
    quizzes = get_top_quizzes(limit)
    return jsonify(quizzes)

@analytics_bp.route('/api/user_activity')
@login_required
@role_required(['analytics_viewer', 'admin'])
def api_user_activity():
    """API endpoint for user activity"""
    days = int(request.args.get('days', 30))
    activity = get_user_activity(days)
    return jsonify(activity)

@analytics_bp.route('/api/quiz-completions')
@login_required
def api_quiz_completions():
    """API endpoint for quiz completion data."""
    if not current_user.has_role('admin') and not current_user.has_role('analytics'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        days = int(request.args.get('days', 30))
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    DATE(completion_date) as date,
                    COUNT(*) as count
                FROM user_scores
                WHERE completion_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                GROUP BY DATE(completion_date)
                ORDER BY date
            """, (days,))
            results = cursor.fetchall()
            
        # Format data for Chart.js
        dates = [row['date'].strftime('%Y-%m-%d') for row in results]
        counts = [row['count'] for row in results]
        
        return jsonify({
            'labels': dates,
            'datasets': [{
                'label': 'Quiz Completions',
                'data': counts,
                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                'borderColor': 'rgba(54, 162, 235, 1)',
                'borderWidth': 1
            }]
        })
    except Exception as e:
        logger.error(f"Error retrieving quiz completion data: {e}")
        return jsonify({'error': str(e)}), 500

# Helper functions for analytics data
def get_summary_metrics():
    """Get summary metrics for the dashboard"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            # Total quizzes
            cursor.execute("SELECT COUNT(*) as count FROM quizzes")
            total_quizzes = cursor.fetchone()['count']
            
            # Total questions
            cursor.execute("SELECT COUNT(*) as count FROM questions")
            total_questions = cursor.fetchone()['count']
            
            # Total quiz attempts
            cursor.execute("SELECT COUNT(*) as count FROM user_scores")
            total_attempts = cursor.fetchone()['count']
            
            # Total users
            cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM user_scores")
            total_users = cursor.fetchone()['count']
            
            # Average score
            cursor.execute("SELECT AVG(score) as avg_score FROM user_scores")
            avg_score = cursor.fetchone()['avg_score'] or 0
            
            # Quiz attempts today
            today = datetime.now().date()
            cursor.execute("SELECT COUNT(*) as count FROM user_scores WHERE DATE(completion_date) = %s", (today,))
            attempts_today = cursor.fetchone()['count']
            
            # Calculate daily trend (% increase/decrease from yesterday)
            yesterday = today - timedelta(days=1)
            cursor.execute("SELECT COUNT(*) as count FROM user_scores WHERE DATE(completion_date) = %s", (yesterday,))
            attempts_yesterday = cursor.fetchone()['count']
            
            if attempts_yesterday > 0:
                daily_trend = ((attempts_today - attempts_yesterday) / attempts_yesterday) * 100
            else:
                daily_trend = 100 if attempts_today > 0 else 0
            
            return {
                'total_quizzes': total_quizzes,
                'total_questions': total_questions,
                'total_attempts': total_attempts,
                'total_users': total_users,
                'avg_score': round(avg_score, 2),
                'attempts_today': attempts_today,
                'daily_trend': round(daily_trend, 2)
            }
    except Exception as e:
        logger.error(f"Error getting summary metrics: {e}")
        # Return default values on error
        return {
            'total_quizzes': 0,
            'total_questions': 0,
            'total_attempts': 0, 
            'total_users': 0,
            'avg_score': 0,
            'attempts_today': 0,
            'daily_trend': 0
        }

def get_top_quizzes(limit=10):
    """Get top quizzes by number of attempts"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            query = """
            SELECT q.quiz_id, q.quiz_name, COUNT(*) as attempts, AVG(us.score) as avg_score
            FROM quizzes q
            JOIN user_scores us ON q.quiz_id = us.quiz_id
            GROUP BY q.quiz_id, q.quiz_name
            ORDER BY attempts DESC
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting top quizzes: {e}")
        return []

def get_recent_activity(limit=10):
    """Get recent quiz activity"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            query = """
            SELECT us.id, us.user_id, us.user_name, q.quiz_id, q.quiz_name, us.score, us.completion_date
            FROM user_scores us
            JOIN quizzes q ON us.quiz_id = q.quiz_id
            ORDER BY us.completion_date DESC
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            activity = cursor.fetchall()
            
            # Convert timestamp to string for JSON serialization
            for entry in activity:
                entry['completion_date'] = entry['completion_date'].isoformat() if entry['completion_date'] else None
            
            return activity
    except Exception as e:
        logger.error(f"Error getting recent activity: {e}")
        return []

def get_user_stats():
    """Get user statistics"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            # Top users by total score
            top_users_query = """
            SELECT user_id, user_name, SUM(score) as total_score, COUNT(*) as quiz_count
            FROM user_scores
            GROUP BY user_id, user_name
            ORDER BY total_score DESC
            LIMIT 10
            """
            cursor.execute(top_users_query)
            top_users = cursor.fetchall()
            
            # Get active hours (when quizzes are taken)
            active_hours_query = """
            SELECT HOUR(completion_date) as hour, COUNT(*) as count
            FROM user_scores
            GROUP BY HOUR(completion_date)
            ORDER BY hour
            """
            cursor.execute(active_hours_query)
            active_hours = cursor.fetchall()
            
            # Format for chart
            hours_data = [0] * 24
            for entry in active_hours:
                hour = entry['hour']
                if 0 <= hour < 24:
                    hours_data[hour] = entry['count']
            
            return {
                'top_users': top_users,
                'active_hours': hours_data
            }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'top_users': [], 'active_hours': [0] * 24}
    finally:
        conn.close()

def get_quiz_activity(days=30):
    """Get quiz activity over time"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days-1)
            
            # Generate all dates in range
            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date)
                current_date += timedelta(days=1)
            
            # Query activity by date
            query = """
            SELECT DATE(completion_date) as date, COUNT(*) as count
            FROM user_scores
            WHERE completion_date >= %s AND completion_date < %s
            GROUP BY DATE(completion_date)
            ORDER BY date
            """
            cursor.execute(query, (start_date, end_date + timedelta(days=1)))
            activity_data = cursor.fetchall()
            
            # Convert to dictionary for easier lookup
            activity_by_date = {entry['date'].isoformat(): entry['count'] for entry in activity_data}
            
            # Format for chart
            result = []
            for date in date_range:
                date_str = date.isoformat()
                result.append({
                    'date': date_str,
                    'count': activity_by_date.get(date_str, 0)
                })
            
            return result
    except Exception as e:
        logger.error(f"Error getting quiz activity: {e}")
        return []

def get_user_activity(days=30):
    """Get user activity over time"""
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days-1)
            
            # Query unique users by date
            query = """
            SELECT DATE(completion_date) as date, COUNT(DISTINCT user_id) as count
            FROM user_scores
            WHERE completion_date >= %s AND completion_date < %s
            GROUP BY DATE(completion_date)
            ORDER BY date
            """
            cursor.execute(query, (start_date, end_date + timedelta(days=1)))
            activity_data = cursor.fetchall()
            
            # Create a lookup dictionary
            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date)
                current_date += timedelta(days=1)
            
            # Convert to dictionary for easier lookup
            activity_by_date = {entry['date'].isoformat(): entry['count'] for entry in activity_data}
            
            # Format for chart
            result = []
            for date in date_range:
                date_str = date.isoformat()
                result.append({
                    'date': date_str,
                    'count': activity_by_date.get(date_str, 0)
                })
            
            return result
    except Exception as e:
        logger.error(f"Error getting user activity: {e}")
        return [] 