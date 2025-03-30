import logging
import json
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models.db import get_db

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

@api_bp.route('/health')
def health_check():
    """API health check endpoint."""
    return jsonify({'status': 'healthy'}), 200

@api_bp.route('/quizzes')
@login_required
def get_quizzes():
    """Get all quizzes for the current user."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get quizzes created by the user or all quizzes for admins
            if current_user.has_role('admin'):
                cursor.execute("""
                    SELECT q.quiz_id, q.quiz_name, q.creator_id, u.username as creator_name, 
                           COUNT(qu.question_id) as question_count, q.created_at
                    FROM quizzes q
                    LEFT JOIN dashboard_users u ON q.creator_id = u.discord_id
                    LEFT JOIN questions qu ON q.quiz_id = qu.quiz_id
                    GROUP BY q.quiz_id
                    ORDER BY q.created_at DESC
                """)
            else:
                cursor.execute("""
                    SELECT q.quiz_id, q.quiz_name, q.creator_id, u.username as creator_name, 
                           COUNT(qu.question_id) as question_count, q.created_at
                    FROM quizzes q
                    LEFT JOIN dashboard_users u ON q.creator_id = u.discord_id
                    LEFT JOIN questions qu ON q.quiz_id = qu.quiz_id
                    WHERE q.creator_id = %s
                    GROUP BY q.quiz_id
                    ORDER BY q.created_at DESC
                """, (current_user.discord_id,))
                
            quizzes = cursor.fetchall()
            
            # Format dates for JSON serialization
            for quiz in quizzes:
                if 'created_at' in quiz and quiz['created_at']:
                    quiz['created_at'] = quiz['created_at'].isoformat()
            
        return jsonify({'quizzes': quizzes})
    except Exception as e:
        logger.error(f"Error getting quizzes: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/quizzes/<int:quiz_id>')
@login_required
def get_quiz(quiz_id):
    """Get details for a specific quiz."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get quiz details
            cursor.execute("""
                SELECT q.*, u.username as creator_name
                FROM quizzes q
                LEFT JOIN dashboard_users u ON q.creator_id = u.discord_id
                WHERE q.quiz_id = %s
            """, (quiz_id,))
            quiz = cursor.fetchone()
            
            if not quiz:
                return jsonify({'error': 'Quiz not found'}), 404
                
            # Check if user has permission to view this quiz
            if not current_user.has_role('admin') and quiz['creator_id'] != current_user.discord_id:
                return jsonify({'error': 'Permission denied'}), 403
                
            # Format dates for JSON serialization
            if 'created_at' in quiz and quiz['created_at']:
                quiz['created_at'] = quiz['created_at'].isoformat()
                
            # Get quiz questions
            cursor.execute("""
                SELECT question_id, question, options, correct_answer, explanation, score
                FROM questions
                WHERE quiz_id = %s
                ORDER BY question_id
            """, (quiz_id,))
            questions = cursor.fetchall()
            
            # Process options from string to list
            for q in questions:
                if q['options']:
                    q['options'] = q['options'].split('|')
                else:
                    q['options'] = []
                    
            quiz['questions'] = questions
            
        return jsonify({'quiz': quiz})
    except Exception as e:
        logger.error(f"Error getting quiz: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/quizzes/<int:quiz_id>/questions', methods=['POST'])
@login_required
def add_question(quiz_id):
    """Add a question to a quiz."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        question_text = data.get('question')
        options = data.get('options', [])
        correct_answer = data.get('correct_answer')
        explanation = data.get('explanation')
        score = data.get('score', 1)
        
        # Validate inputs
        if not question_text:
            return jsonify({'error': 'Question text is required'}), 400
            
        if len(options) < 2:
            return jsonify({'error': 'At least two options are required'}), 400
            
        if correct_answer is None or int(correct_answer) >= len(options):
            return jsonify({'error': 'A valid correct answer is required'}), 400
        
        conn = get_db()
        with conn.cursor() as cursor:
            # Get quiz details to check permissions
            cursor.execute(
                "SELECT creator_id FROM quizzes WHERE quiz_id = %s",
                (quiz_id,)
            )
            quiz = cursor.fetchone()
            
            if not quiz:
                return jsonify({'error': 'Quiz not found'}), 404
                
            # Check if user has permission to edit this quiz
            if not current_user.has_role('admin') and quiz['creator_id'] != current_user.discord_id:
                return jsonify({'error': 'Permission denied'}), 403
                
            # Join options as pipe-separated string
            options_str = '|'.join(options)
            
            # Insert the question
            cursor.execute("""
                INSERT INTO questions (quiz_id, question, options, correct_answer, explanation, score)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (quiz_id, question_text, options_str, correct_answer, explanation, score))
            question_id = cursor.lastrowid
            conn.commit()
            
        return jsonify({
            'success': True,
            'question_id': question_id,
            'message': 'Question added successfully'
        })
    except Exception as e:
        logger.error(f"Error adding question: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/questions/<int:question_id>', methods=['PUT'])
@login_required
def update_question(question_id):
    """Update a specific question."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        question_text = data.get('question')
        options = data.get('options', [])
        correct_answer = data.get('correct_answer')
        explanation = data.get('explanation')
        score = data.get('score', 1)
        
        # Validate inputs
        if not question_text:
            return jsonify({'error': 'Question text is required'}), 400
            
        if len(options) < 2:
            return jsonify({'error': 'At least two options are required'}), 400
            
        if correct_answer is None or int(correct_answer) >= len(options):
            return jsonify({'error': 'A valid correct answer is required'}), 400
        
        conn = get_db()
        with conn.cursor() as cursor:
            # Get question details to check permissions
            cursor.execute("""
                SELECT q.quiz_id, qz.creator_id
                FROM questions q
                JOIN quizzes qz ON q.quiz_id = qz.quiz_id
                WHERE q.question_id = %s
            """, (question_id,))
            question = cursor.fetchone()
            
            if not question:
                return jsonify({'error': 'Question not found'}), 404
                
            # Check if user has permission to edit this question
            if not current_user.has_role('admin') and question['creator_id'] != current_user.discord_id:
                return jsonify({'error': 'Permission denied'}), 403
                
            # Join options as pipe-separated string
            options_str = '|'.join(options)
            
            # Update the question
            cursor.execute("""
                UPDATE questions
                SET question = %s, options = %s, correct_answer = %s, explanation = %s, score = %s
                WHERE question_id = %s
            """, (question_text, options_str, correct_answer, explanation, score, question_id))
            conn.commit()
            
        return jsonify({
            'success': True,
            'message': 'Question updated successfully'
        })
    except Exception as e:
        logger.error(f"Error updating question: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/questions/<int:question_id>', methods=['DELETE'])
@login_required
def delete_question(question_id):
    """Delete a specific question."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get question details to check permissions
            cursor.execute("""
                SELECT q.quiz_id, qz.creator_id
                FROM questions q
                JOIN quizzes qz ON q.quiz_id = qz.quiz_id
                WHERE q.question_id = %s
            """, (question_id,))
            question = cursor.fetchone()
            
            if not question:
                return jsonify({'error': 'Question not found'}), 404
                
            # Check if user has permission to delete this question
            if not current_user.has_role('admin') and question['creator_id'] != current_user.discord_id:
                return jsonify({'error': 'Permission denied'}), 403
                
            # Delete the question
            cursor.execute(
                "DELETE FROM questions WHERE question_id = %s",
                (question_id,)
            )
            conn.commit()
            
        return jsonify({
            'success': True,
            'message': 'Question deleted successfully'
        })
    except Exception as e:
        logger.error(f"Error deleting question: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/stats/user')
@login_required
def get_user_stats():
    """Get statistics for the current user."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get quiz count created by user
            cursor.execute(
                "SELECT COUNT(*) as count FROM quizzes WHERE creator_id = %s",
                (current_user.discord_id,)
            )
            quiz_count = cursor.fetchone()['count']
            
            # Get question count created by user
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM questions q
                JOIN quizzes qz ON q.quiz_id = qz.quiz_id
                WHERE qz.creator_id = %s
            """, (current_user.discord_id,))
            question_count = cursor.fetchone()['count']
            
            # Get quizzes taken by user
            cursor.execute(
                "SELECT COUNT(*) as count FROM user_scores WHERE user_id = %s",
                (current_user.discord_id,)
            )
            quizzes_taken = cursor.fetchone()['count']
            
            # Get average score
            cursor.execute(
                "SELECT AVG(score) as avg_score FROM user_scores WHERE user_id = %s",
                (current_user.discord_id,)
            )
            result = cursor.fetchone()
            avg_score = result['avg_score'] if result['avg_score'] is not None else 0
            
            # Get recent activity
            cursor.execute("""
                SELECT s.*, q.quiz_name
                FROM user_scores s
                JOIN quizzes q ON s.quiz_id = q.quiz_id
                WHERE s.user_id = %s
                ORDER BY s.completion_date DESC
                LIMIT 5
            """, (current_user.discord_id,))
            recent_activity = cursor.fetchall()
            
            # Format dates for JSON serialization
            for activity in recent_activity:
                if 'completion_date' in activity and activity['completion_date']:
                    activity['completion_date'] = activity['completion_date'].isoformat()
                if 'started_at' in activity and activity['started_at']:
                    activity['started_at'] = activity['started_at'].isoformat()
            
        return jsonify({
            'quiz_count': quiz_count,
            'question_count': question_count,
            'quizzes_taken': quizzes_taken,
            'avg_score': avg_score,
            'recent_activity': recent_activity
        })
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/quiz-completions')
@login_required
def quiz_completions():
    """API endpoint for quiz completion data."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT us.*, q.quiz_name 
                FROM user_scores us
                JOIN quizzes q ON us.quiz_id = q.quiz_id
                WHERE us.user_id = %s
                ORDER BY us.completion_date DESC
                LIMIT 10
            """, (current_user.discord_id,))
            completions = cursor.fetchall()
            
            # Process dates for JSON serialization
            for item in completions:
                if 'completion_date' in item and item['completion_date']:
                    item['completion_date'] = item['completion_date'].isoformat()
            
        return jsonify(completions)
    except Exception as e:
        logger.error(f"Error retrieving quiz completions: {e}")
        return jsonify({"error": str(e)}), 500 