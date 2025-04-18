import logging
import math
from flask import Blueprint, flash, render_template, jsonify, request
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
                SELECT
                    q.quiz_id, q.quiz_name,
                    q.creator_username as creator,
                    COUNT(DISTINCT us.id) as attempts,
                    AVG(us.score) as avg_raw_score,
                    AVG(
                        CASE
                            WHEN qt.total_score IS NOT NULL AND qt.total_score > 0 THEN (us.score * 100.0 / qt.total_score)
                            ELSE 0
                        END
                    ) as avg_score_percentage,
                    COUNT(DISTINCT qu.question_id) as question_count,
                    COALESCE(qt.total_score, 0) as total_points -- Add total points here
                FROM quizzes q
                LEFT JOIN user_scores us ON q.quiz_id = us.quiz_id
                LEFT JOIN questions qu ON q.quiz_id = qu.quiz_id
                LEFT JOIN (
                    SELECT quiz_id, SUM(score) as total_score
                    FROM questions
                    GROUP BY quiz_id
                ) qt ON q.quiz_id = qt.quiz_id
                GROUP BY q.quiz_id, q.quiz_name, q.creator_username, qt.total_score -- Group by total_score too
                ORDER BY attempts DESC
            """)
            quiz_data = cursor.fetchall()

            # Format the data
            for quiz in quiz_data:
                quiz['avg_raw_score'] = round(quiz['avg_raw_score'], 1) if quiz['avg_raw_score'] is not None else 0
                quiz['avg_score_percentage'] = round(quiz['avg_score_percentage'], 1) if quiz['avg_score_percentage'] is not None else 0
                quiz['avg_score'] = quiz['avg_score_percentage']
                # Ensure total_points is present (already handled by COALESCE in SQL)

    except Exception as e:
        logger.error(f"Error fetching quiz analytics: {e}", exc_info=True)

    return render_template('analytics/quizzes.html', quizzes=quiz_data)

@analytics_bp.route('/users')
@login_required
@role_required(['analytics_viewer', 'admin'])
def users():
    """Show user analytics with filtering, sorting, and pagination."""
    conn = get_db()
    user_data = []
    quizzes_list = []
    total_users = 0
    limit = 20 # Default items per page
    active_hours_data = [0] * 24 # Initialize default
    page = 1
    quiz_filter = None
    sort_by = 'quizzes_taken'
    sort_order = 'desc'
    total_pages = 0

    # Initialize pagination and sort_params dictionaries
    pagination = {'page': 1, 'per_page': limit, 'total_users': 0, 'total_pages': 0}
    sort_params = {'sort_by': 'quizzes_taken', 'sort_order': 'desc'}

    try:
        # --- Get Filter/Sort/Pagination Parameters ---
        page = request.args.get('page', 1, type=int)
        quiz_filter = request.args.get('quiz_filter', None, type=int)
        sort_by = request.args.get('sort_by', 'quizzes_taken')
        sort_order = request.args.get('sort_order', 'desc')

        # Update sort_params dictionary after getting args
        sort_params = {'sort_by': sort_by, 'sort_order': sort_order}

        # Validate sort_order
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
            sort_params['sort_order'] = 'desc' # Update dict too

        # Map sort_by parameter to actual DB columns/aliases to prevent injection
        allowed_sort_columns = {
            'username': 'us.user_name',
            'quizzes_taken': 'quizzes_taken',
            'avg_score_percentage': 'avg_score_percentage',
            'avg_raw_score': 'avg_raw_score',
            'last_active': 'last_active'
        }
        order_by_column = allowed_sort_columns.get(sort_by, 'quizzes_taken')

        # Calculate OFFSET for pagination
        offset = (page - 1) * limit

        # --- Fetch Quizzes for Filter Dropdown ---
        with conn.cursor() as cursor:
            cursor.execute("SELECT quiz_id, quiz_name FROM quizzes ORDER BY quiz_name ASC")
            quizzes_list = cursor.fetchall()

        # --- Fetch User Stats for Charts ---
        user_stats = get_user_stats() # Call helper function
        # Add robust check for user_stats and active_hours key
        if isinstance(user_stats, dict):
             temp_active_hours = user_stats.get('active_hours') # Get value first
             if isinstance(temp_active_hours, list):
                 active_hours_data = temp_active_hours # Assign if it's a list
             else:
                 logger.warning(f"get_user_stats returned 'active_hours' that is not a list: {temp_active_hours}. Falling back to default.")
                 # Keep the initialized default
        else:
             logger.error(f"get_user_stats did not return a dictionary: {user_stats}. Falling back to default active_hours.")
             # Keep the initialized default

        # --- Build SQL Query ---
        base_query = """
            SELECT
                us.user_id as discord_id,
                us.user_name as username,
                COUNT(us.id) as quizzes_taken,
                AVG(us.score) as avg_raw_score,
                AVG(
                    CASE
                        WHEN qt.total_score IS NOT NULL AND qt.total_score > 0 THEN (us.score * 100.0 / qt.total_score)
                        ELSE 0
                    END
                ) as avg_score_percentage,
                MAX(us.completion_date) as last_active
            FROM user_scores us
            JOIN quizzes q ON us.quiz_id = q.quiz_id
            LEFT JOIN (
                SELECT quiz_id, SUM(score) as total_score
                FROM questions
                GROUP BY quiz_id
            ) qt ON us.quiz_id = qt.quiz_id
        """
        count_query = "SELECT COUNT(DISTINCT us.user_id) as total FROM user_scores us"
        params = []
        where_clauses = []

        # Apply quiz filter if provided
        if quiz_filter:
            where_clauses.append("us.quiz_id = %s")
            params.append(quiz_filter)

        # Add WHERE clauses to queries
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)
            base_query += where_sql
            count_query += where_sql # Add filter to count query as well

        # Add Group By
        base_query += " GROUP BY us.user_id, us.user_name"

        # Add Order By
        base_query += f" ORDER BY {order_by_column} {sort_order.upper()}, us.user_name ASC" # Add secondary sort

        # Add Limit and Offset for pagination
        base_query += " LIMIT %s OFFSET %s"
        count_params = params[:] # Copy params for count query *before* adding limit/offset
        params.extend([limit, offset]) # Add limit and offset to params list

        # --- Execute Queries ---
        with conn.cursor() as cursor:
            # Fetch total count first (using the same filter)
            cursor.execute(count_query, count_params) # Use copied params
            total_users = cursor.fetchone()['total'] or 0

            # Fetch user data for the current page
            cursor.execute(base_query, params)
            user_data = cursor.fetchall()

        # Calculate total pages
        total_pages = math.ceil(total_users / limit)

        # Update pagination dict
        pagination = {'page': page, 'per_page': limit, 'total_users': total_users, 'total_pages': total_pages}

        # --- Format Data ---
        for user in user_data:
            user['avg_raw_score'] = round(user['avg_raw_score'], 1) if user['avg_raw_score'] is not None else 0
            user['avg_score_percentage'] = round(user['avg_score_percentage'], 1) if user['avg_score_percentage'] is not None else 0
            user['avg_score'] = user['avg_score_percentage'] # Keep for compatibility if needed

    except Exception as e:
        logger.error(f"Error fetching user analytics: {e}", exc_info=True)
        flash("An error occurred while fetching user analytics.", "danger")
        # pagination/sort_params retain initial values, active_hours_data retains initial value or value from get_user_stats

    # Final check before rendering
    if not isinstance(active_hours_data, list):
        logger.error(f"active_hours_data is not a list before rendering: {type(active_hours_data)}. Forcing default.")
        active_hours_data = [0] * 24

    return render_template(
        'analytics/users.html',
        users=user_data,
        quizzes=quizzes_list, # Pass quiz list for filter
        current_quiz_filter=quiz_filter, # Pass current filter
        pagination=pagination, # Pass the dictionary
        sort_params=sort_params, # Pass the dictionary
        active_hours=active_hours_data # Pass the verified/defaulted list
    )

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

@analytics_bp.route('/tribbles')
@login_required
@role_required(['analytics_viewer', 'admin'])
def tribbles():
    """Show tribble hunt analytics"""
    conn = get_db()
    events = []
    top_hunters = []
    stats = {
        'total_drops': 0,
        'total_claimed': 0,
        'total_escaped': 0,
        'active_events': 0,
        'participant_count': 0  # Added participant count
    }
    rarity_distribution = [0, 0, 0, 0, 0]  # Common, Uncommon, Rare, Epic, Legendary
    activity_data = []  # For activity chart

    try:
        with conn.cursor() as cursor:
            # Get recent events
            cursor.execute("""
                SELECT 
                    id, event_id, active, start_time, end_time, 
                    guild_id, event_name
                FROM tribble_event
                ORDER BY start_time DESC
                LIMIT 10
            """)
            events = cursor.fetchall()
            
            # Count active events
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM tribble_event
                WHERE active = 1
            """)
            active_events = cursor.fetchone()
            if active_events:
                stats['active_events'] = active_events['count']
            
            # Get drop statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN claimed_by IS NOT NULL THEN 1 ELSE 0 END) as claimed,
                    SUM(CASE WHEN is_escaped = 1 THEN 1 ELSE 0 END) as escape_count
                FROM tribble_drops
            """)
            drop_stats = cursor.fetchone()
            if drop_stats:
                stats['total_drops'] = drop_stats['total'] or 0
                stats['total_claimed'] = drop_stats['claimed'] or 0
                stats['total_escaped'] = drop_stats['escape_count'] or 0
            
            # Count unique participants
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as participant_count
                FROM tribble_scores
            """)
            participant_count = cursor.fetchone()
            if participant_count:
                stats['participant_count'] = participant_count['participant_count'] or 0
            
            # Get rarity distribution
            cursor.execute("""
                SELECT rarity, COUNT(*) as count
                FROM tribble_drops
                GROUP BY rarity
                ORDER BY rarity
            """)
            rarity_counts = cursor.fetchall()
            
            # Map rarity values to positions in the distribution array
            for rarity in rarity_counts:
                rarity_value = rarity['rarity']
                if 1 <= rarity_value <= 5:
                    rarity_distribution[rarity_value-1] = rarity['count']
            
            # Get top hunters - use username column from tribble_scores directly
            cursor.execute("""
                SELECT 
                    ts.user_id,
                    COALESCE(ts.username, CONCAT('User ', ts.user_id)) as username,
                    ts.score,
                    COUNT(td.message_id) as tribbles_caught
                FROM tribble_scores ts
                LEFT JOIN tribble_drops td ON ts.user_id = td.claimed_by
                GROUP BY ts.user_id, ts.username, ts.score
                ORDER BY ts.score DESC
                LIMIT 10
            """)
            top_hunters_data = cursor.fetchall()
            
            # Format hunter data
            for hunter in top_hunters_data:
                top_hunters.append({
                    'username': hunter['username'],
                    'score': hunter['score'],
                    'tribbles_caught': hunter['tribbles_caught'] or 0
                })
            
            # Get activity data with hourly precision instead of just per day
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(captured_at, '%Y-%m-%d %H:00:00') as time_period,
                    COUNT(*) as total,
                    SUM(CASE WHEN claimed_by IS NOT NULL THEN 1 ELSE 0 END) as claimed,
                    SUM(CASE WHEN is_escaped = 1 THEN 1 ELSE 0 END) as escape_count
                FROM tribble_drops
                WHERE captured_at IS NOT NULL
                GROUP BY time_period
                ORDER BY time_period DESC
                LIMIT 48
            """)
            activity_results = cursor.fetchall()
            
            # Reverse the results to show oldest to newest
            for result in reversed(activity_results):
                activity_data.append({
                    'time_period': result['time_period'],
                    'total': result['total'],
                    'claimed': result['claimed'] or 0,
                    'escaped': result['escape_count'] or 0
                })
                
    except Exception as e:
        logger.error(f"Error fetching tribble hunt analytics: {e}", exc_info=True)
        flash("An error occurred while fetching tribble hunt analytics.", "danger")

    return render_template(
        'analytics/tribbles.html',
        events=events,
        top_hunters=top_hunters,
        stats=stats,
        rarity_distribution=rarity_distribution,
        activity_data=activity_data
    )

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
            cursor.execute("""
                SELECT AVG(score_percentage) as avg_score_percentage
                FROM (
                    SELECT
                        CASE
                            WHEN qt.total_score IS NOT NULL AND qt.total_score > 0 THEN (us.score * 100.0 / qt.total_score)
                            ELSE 0
                        END as score_percentage
                    FROM user_scores us
                    JOIN quizzes q ON us.quiz_id = q.quiz_id
                    LEFT JOIN (
                        SELECT quiz_id, SUM(score) as total_score
                        FROM questions
                        GROUP BY quiz_id
                    ) qt ON q.quiz_id = qt.quiz_id
                ) AS score_percentages
            """)
            result = cursor.fetchone()
            # Use the calculated average percentage
            avg_score = result['avg_score_percentage'] or 0
            
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
            # Use f-string for LIMIT, ensure limit is integer
            # Calculate average score percentage per quiz
            query = f"""
            SELECT
                q.quiz_id,
                q.quiz_name,
                COUNT(us.id) as attempts,
                AVG(
                    CASE
                        WHEN qt.total_score IS NOT NULL AND qt.total_score > 0 THEN (us.score * 100.0 / qt.total_score)
                        ELSE 0
                    END
                ) as avg_score_percentage
            FROM quizzes q
            JOIN user_scores us ON q.quiz_id = us.quiz_id
            LEFT JOIN (
                SELECT quiz_id, SUM(score) as total_score
                FROM questions
                GROUP BY quiz_id
            ) qt ON q.quiz_id = qt.quiz_id
            GROUP BY q.quiz_id, q.quiz_name -- Include qt.total_score if needed for debugging, but not necessary for grouping here
            ORDER BY attempts DESC
            LIMIT {int(limit)}
            """
            cursor.execute(query)
            quizzes = cursor.fetchall()

            # Format the data (round the avg_score_percentage)
            for quiz in quizzes:
                 quiz['avg_score'] = round(quiz.pop('avg_score_percentage'), 1) # Rename key and round

            return quizzes
    except Exception as e:
        logger.error(f"Error getting top quizzes: {e}", exc_info=True)
        return []


def get_recent_activity(limit=10):
    """Get recent quiz activity"""
    conn = get_db()

    try:
        with conn.cursor() as cursor:
            # Use f-string for LIMIT, ensuring limit is an integer
            query = f"""
            SELECT
                us.id, us.user_id, us.user_name as username,
                q.quiz_id, q.quiz_name,
                CASE
                    WHEN qt.total_score IS NOT NULL AND qt.total_score > 0 THEN (us.score * 100.0 / qt.total_score)
                    ELSE 0 -- Assign 0% if total_score is 0 or null
                END as score_percentage,
                us.completion_date
            FROM user_scores us
            JOIN quizzes q ON us.quiz_id = q.quiz_id
            LEFT JOIN (
                SELECT quiz_id, SUM(score) as total_score
                FROM questions
                GROUP BY quiz_id
            ) qt ON q.quiz_id = qt.quiz_id
            ORDER BY us.completion_date DESC
            LIMIT {int(limit)} -- Format limit directly into query
            """
            # Execute the query without the limit parameter
            cursor.execute(query)
            activity = cursor.fetchall()

            # Format the data
            for entry in activity:
                entry['score_percentage'] = round(entry['score_percentage'], 1) if entry['score_percentage'] is not None else 0
                entry['completion_date'] = entry['completion_date'].isoformat() if entry['completion_date'] else None

            return activity
    except Exception as e:
        logger.error(f"Error getting recent activity: {e}", exc_info=True)
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