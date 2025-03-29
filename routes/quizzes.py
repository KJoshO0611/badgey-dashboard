import logging
from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from flask_login import login_required, current_user
import json
from models.quiz import Quiz, QuizNotFoundError
from decorators import role_required
from models.db import get_db

logger = logging.getLogger(__name__)

quizzes_bp = Blueprint('quizzes', __name__, url_prefix='/quizzes')

@quizzes_bp.route('/')
@login_required
def list():
    """List all quizzes for the current user."""
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
            
        return render_template('quizzes/list.html', quizzes=quizzes)
    except Exception as e:
        logger.error(f"Error listing quizzes: {e}")
        flash("An error occurred while retrieving quizzes.", "danger")
        return render_template('quizzes/list.html', quizzes=[])

@quizzes_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new quiz."""
    if request.method == 'POST':
        quiz_name = request.form.get('quiz_name')
        
        if not quiz_name:
            flash("Quiz name is required.", "danger")
            return render_template('quizzes/create.html')
            
        try:
            conn = get_db()
            with conn.cursor() as cursor:
                # Check if a quiz with this name already exists
                cursor.execute(
                    "SELECT quiz_id FROM quizzes WHERE quiz_name = %s AND creator_id = %s",
                    (quiz_name, current_user.discord_id)
                )
                if cursor.fetchone():
                    flash("A quiz with this name already exists.", "warning")
                    return render_template('quizzes/create.html')
                    
                # Insert the new quiz
                cursor.execute(
                    "INSERT INTO quizzes (quiz_name, creator_id) VALUES (%s, %s)",
                    (quiz_name, current_user.discord_id)
                )
                quiz_id = cursor.lastrowid
                conn.commit()
                
                flash(f"Quiz '{quiz_name}' created successfully!", "success")
                return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        except Exception as e:
            logger.error(f"Error creating quiz: {e}")
            conn.rollback()
            flash("An error occurred while creating the quiz.", "danger")
            
    return render_template('quizzes/create.html')

@quizzes_bp.route('/<int:quiz_id>')
@login_required
def view(quiz_id):
    """View a specific quiz."""
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
                flash("Quiz not found.", "danger")
                return redirect(url_for('quizzes.list'))
                
            # Check if user has permission to view this quiz
            if not current_user.has_role('admin') and quiz['creator_id'] != current_user.discord_id:
                flash("You don't have permission to view this quiz.", "danger")
                return redirect(url_for('quizzes.list'))
                
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
                    
        return render_template('quizzes/view.html', quiz=quiz, questions=questions)
    except Exception as e:
        logger.error(f"Error viewing quiz: {e}")
        flash("An error occurred while retrieving the quiz.", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(quiz_id):
    """Edit a specific quiz."""
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
                flash("Quiz not found.", "danger")
                return redirect(url_for('quizzes.list'))
                
            # Check if user has permission to edit this quiz
            if not current_user.has_role('admin') and quiz['creator_id'] != current_user.discord_id:
                flash("You don't have permission to edit this quiz.", "danger")
                return redirect(url_for('quizzes.list'))
            
            if request.method == 'POST':
                quiz_name = request.form.get('quiz_name')
                
                if not quiz_name:
                    flash("Quiz name is required.", "danger")
                else:
                    # Update quiz name
                    cursor.execute(
                        "UPDATE quizzes SET quiz_name = %s WHERE quiz_id = %s",
                        (quiz_name, quiz_id)
                    )
                    conn.commit()
                    flash("Quiz updated successfully!", "success")
                    return redirect(url_for('quizzes.view', quiz_id=quiz_id))
                    
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
                    
        return render_template('quizzes/edit.html', quiz=quiz, questions=questions)
    except Exception as e:
        logger.error(f"Error editing quiz: {e}")
        flash("An error occurred while retrieving the quiz.", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/delete', methods=['POST'])
@login_required
def delete(quiz_id):
    """Delete a specific quiz."""
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            # Get quiz details
            cursor.execute(
                "SELECT creator_id FROM quizzes WHERE quiz_id = %s",
                (quiz_id,)
            )
            quiz = cursor.fetchone()
            
            if not quiz:
                flash("Quiz not found.", "danger")
                return redirect(url_for('quizzes.list'))
                
            # Check if user has permission to delete this quiz
            if not current_user.has_role('admin') and quiz['creator_id'] != current_user.discord_id:
                flash("You don't have permission to delete this quiz.", "danger")
                return redirect(url_for('quizzes.list'))
                
            # Delete quiz (cascades to questions)
            cursor.execute(
                "DELETE FROM quizzes WHERE quiz_id = %s",
                (quiz_id,)
            )
            conn.commit()
            flash("Quiz deleted successfully!", "success")
            
        return redirect(url_for('quizzes.list'))
    except Exception as e:
        logger.error(f"Error deleting quiz: {e}")
        flash("An error occurred while deleting the quiz.", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/preview')
@login_required
def preview(quiz_id):
    """Preview how the quiz will appear to users"""
    try:
        quiz = Quiz.get_by_id(quiz_id)
        questions = quiz.get_questions()
        
        return render_template('quizzes/preview.html', quiz=quiz, questions=questions)
    
    except QuizNotFoundError:
        flash('Quiz not found', 'error')
        return redirect(url_for('quizzes.list'))

# API Endpoints for AJAX
@quizzes_bp.route('/api/list')
@login_required
def api_list_quizzes():
    """API endpoint to list quizzes"""
    quizzes = Quiz.get_all()
    return jsonify([q.to_dict() for q in quizzes])

@quizzes_bp.route('/api/<int:quiz_id>')
@login_required
def api_get_quiz(quiz_id):
    """API endpoint to get quiz details"""
    try:
        quiz = Quiz.get_by_id(quiz_id)
        questions = quiz.get_questions()
        
        response = quiz.to_dict()
        response['questions'] = [q.to_dict() for q in questions]
        
        return jsonify(response)
    
    except QuizNotFoundError:
        return jsonify({'error': 'Quiz not found'}), 404 