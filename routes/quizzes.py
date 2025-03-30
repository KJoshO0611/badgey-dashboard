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
        logger.info("Fetching quizzes for list view")
        
        # Get quizzes based on user role
        if current_user.has_role('admin'):
            logger.info("Admin user: fetching all quizzes")
            quizzes = Quiz.get_all()
        else:
            logger.info(f"Regular user: fetching quizzes for user {current_user.discord_id}")
            quizzes = Quiz.get_by_creator(current_user.discord_id)
        
        # Add question counts to each quiz
        for quiz in quizzes:
            quiz.question_count = quiz.get_question_count()
        
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
            # Create quiz using the Quiz model
            logger.info(f"Creating new quiz '{quiz_name}' for user {current_user.discord_id}")
            quiz = Quiz.create(quiz_name, current_user.discord_id)
            
            flash(f"Quiz '{quiz_name}' created successfully!", "success")
            return redirect(url_for('quizzes.edit', quiz_id=quiz.id))
        except Exception as e:
            logger.error(f"Error creating quiz: {e}")
            flash("An error occurred while creating the quiz.", "danger")
            
    return render_template('quizzes/create.html')

@quizzes_bp.route('/<int:quiz_id>')
@login_required
def view(quiz_id):
    """View a specific quiz."""
    try:
        # Fetch the quiz directly with Quiz model
        try:
            logger.info(f"Fetching quiz with ID {quiz_id} for viewing")
            quiz = Quiz.get_by_id(quiz_id)
            
            # Check if user has permission to view this quiz
            if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
                logger.warning(f"User {current_user.discord_id} attempted to view quiz {quiz_id} without permission")
                flash("You don't have permission to view this quiz.", "danger")
                return redirect(url_for('quizzes.list'))
            
            logger.info(f"Fetching questions for quiz {quiz_id}")
            questions = quiz.get_questions()
            
            return render_template('quizzes/view.html', quiz=quiz, questions=questions)
        except Exception as e:
            logger.error(f"Error viewing quiz with model approach: {e}")
            # Fallback to direct database query
            raise e
    except Exception as e:
        logger.error(f"Error viewing quiz: {e}")
        flash("An error occurred while retrieving the quiz.", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(quiz_id):
    """Edit a specific quiz."""
    try:
        # Fetch the quiz directly with Quiz model
        try:
            logger.info(f"Fetching quiz with ID {quiz_id} for editing")
            quiz = Quiz.get_by_id(quiz_id)
            
            # Check if user has permission to edit this quiz
            if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
                logger.warning(f"User {current_user.discord_id} attempted to edit quiz {quiz_id} without permission")
                flash("You don't have permission to edit this quiz.", "danger")
                return redirect(url_for('quizzes.list'))
            
            if request.method == 'POST':
                quiz_name = request.form.get('quiz_name')
                
                if not quiz_name:
                    flash("Quiz name is required.", "danger")
                else:
                    # Update quiz name
                    logger.info(f"Updating quiz {quiz_id} name to {quiz_name}")
                    quiz.update(quiz_name)
                    flash("Quiz updated successfully!", "success")
                    return redirect(url_for('quizzes.view', quiz_id=quiz_id))
            
            logger.info(f"Fetching questions for quiz {quiz_id}")
            questions = quiz.get_questions()
            
            return render_template('quizzes/edit.html', quiz=quiz, questions=questions)
        except Exception as e:
            logger.error(f"Error editing quiz with model approach: {e}")
            # Fallback to direct database query
            raise e
    except Exception as e:
        logger.error(f"Error editing quiz: {e}")
        flash("An error occurred while retrieving the quiz.", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/delete', methods=['POST'])
@login_required
def delete(quiz_id):
    """Delete a specific quiz."""
    try:
        logger.info(f"Attempting to delete quiz {quiz_id}")
        quiz = Quiz.get_by_id(quiz_id)
        
        # Check if user has permission to delete this quiz
        if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
            logger.warning(f"User {current_user.discord_id} attempted to delete quiz {quiz_id} without permission")
            flash("You don't have permission to delete this quiz.", "danger")
            return redirect(url_for('quizzes.list'))
        
        # Delete the quiz using the model
        logger.info(f"Deleting quiz {quiz_id}")
        quiz.delete()
        flash("Quiz deleted successfully!", "success")
        
        return redirect(url_for('quizzes.list'))
    except QuizNotFoundError:
        logger.error(f"Quiz with ID {quiz_id} not found for deletion")
        flash("Quiz not found.", "danger")
        return redirect(url_for('quizzes.list'))
    except Exception as e:
        logger.error(f"Error deleting quiz {quiz_id}: {e}")
        flash("An error occurred while deleting the quiz.", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/preview')
@login_required
def preview(quiz_id):
    """Preview how the quiz will appear to users"""
    try:
        # Add detailed logging
        logger.info(f"Fetching quiz with ID {quiz_id} for preview")
        quiz = Quiz.get_by_id(quiz_id)
        
        logger.info(f"Fetching questions for quiz {quiz_id}")
        questions = quiz.get_questions()
        
        return render_template('quizzes/preview.html', quiz=quiz, questions=questions)
    
    except QuizNotFoundError:
        logger.error(f"Quiz with ID {quiz_id} not found")
        flash('Quiz not found', 'error')
        return redirect(url_for('quizzes.list'))
    except Exception as e:
        logger.error(f"Error previewing quiz {quiz_id}: {e}")
        flash(f"An error occurred while previewing the quiz: {str(e)}", "danger")
        return redirect(url_for('quizzes.list'))

@quizzes_bp.route('/<int:quiz_id>/questions/add', methods=['POST'])
@login_required
def add_question(quiz_id):
    """Add a new question to a quiz."""
    try:
        logger.info(f"Adding question to quiz {quiz_id}")
        quiz = Quiz.get_by_id(quiz_id)
        
        # Check if user has permission to edit this quiz
        if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
            logger.warning(f"User {current_user.discord_id} attempted to add question to quiz {quiz_id} without permission")
            flash("You don't have permission to edit this quiz.", "danger")
            return redirect(url_for('quizzes.list'))
        
        # Extract form data
        question_text = request.form.get('question')
        
        # Process lettered options (A, B, C, etc.)
        options = {}
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for letter in letters:
            if f'option{letter}' in request.form:
                option_value = request.form.get(f'option{letter}')
                if option_value.strip():  # Only add non-empty options
                    options[letter] = option_value
        
        # Get correct answer and score
        correct_answer = request.form.get('correct_answer', 'A')
        score = request.form.get('score', 10)
        explanation = request.form.get('explanation', '')
        
        # Validate inputs
        if not question_text:
            flash("Question text is required.", "danger")
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
            
        if len(options) < 2:
            flash("At least two options are required.", "danger")
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
            
        # Add the question
        logger.info(f"Creating question for quiz {quiz_id}")
        quiz.add_question(
            text=question_text,
            options=options,
            correct_answer=correct_answer,
            score=int(score),
            explanation=explanation
        )
        
        flash("Question added successfully!", "success")
        return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
    except Exception as e:
        logger.error(f"Error adding question to quiz {quiz_id}: {e}")
        flash("An error occurred while adding the question.", "danger")
        return redirect(url_for('quizzes.edit', quiz_id=quiz_id))

@quizzes_bp.route('/<int:quiz_id>/questions/<int:question_id>/edit', methods=['POST'])
@login_required
def edit_question(quiz_id, question_id):
    """Edit an existing question."""
    try:
        logger.info(f"Editing question {question_id} for quiz {quiz_id}")
        quiz = Quiz.get_by_id(quiz_id)
        
        # Check if user has permission to edit this quiz
        if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
            logger.warning(f"User {current_user.discord_id} attempted to edit quiz {quiz_id} without permission")
            flash("You don't have permission to edit this quiz.", "danger")
            return redirect(url_for('quizzes.list'))
        
        # Find the question
        question = None
        for q in quiz.get_questions():
            if q.id == question_id:
                question = q
                break
                
        if not question:
            flash("Question not found.", "danger")
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        # Extract form data
        question_text = request.form.get('question')
        
        # Process lettered options (A, B, C, etc.)
        options = {}
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for letter in letters:
            if f'option{letter}' in request.form:
                option_value = request.form.get(f'option{letter}')
                if option_value.strip():  # Only add non-empty options
                    options[letter] = option_value
        
        # Get correct answer and score
        correct_answer = request.form.get('correct_answer', 'A')
        score = request.form.get('score', 10)
        explanation = request.form.get('explanation', '')
        
        # Validate inputs
        if not question_text:
            flash("Question text is required.", "danger")
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
            
        if len(options) < 2:
            flash("At least two options are required.", "danger")
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        # Update the question
        logger.info(f"Updating question {question_id} for quiz {quiz_id}")
        question.update(
            text=question_text,
            options=options,
            correct_answer=correct_answer,
            score=int(score),
            explanation=explanation
        )
        
        flash("Question updated successfully!", "success")
        return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
    except Exception as e:
        logger.error(f"Error editing question {question_id} for quiz {quiz_id}: {e}")
        flash("An error occurred while updating the question.", "danger")
        return redirect(url_for('quizzes.edit', quiz_id=quiz_id))

@quizzes_bp.route('/<int:quiz_id>/questions/<int:question_id>/delete', methods=['POST'])
@login_required
def delete_question(quiz_id, question_id):
    """Delete a question from a quiz."""
    try:
        logger.info(f"Deleting question {question_id} from quiz {quiz_id}")
        quiz = Quiz.get_by_id(quiz_id)
        
        # Check if user has permission to edit this quiz
        if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
            logger.warning(f"User {current_user.discord_id} attempted to delete question from quiz {quiz_id} without permission")
            flash("You don't have permission to edit this quiz.", "danger")
            return redirect(url_for('quizzes.list'))
        
        # Find the question
        question = None
        for q in quiz.get_questions():
            if q.id == question_id:
                question = q
                break
                
        if not question:
            flash("Question not found.", "danger")
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        # Delete the question
        logger.info(f"Deleting question {question_id} from quiz {quiz_id}")
        question.delete()
        
        flash("Question deleted successfully!", "success")
        return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
    except Exception as e:
        logger.error(f"Error deleting question {question_id} from quiz {quiz_id}: {e}")
        flash("An error occurred while deleting the question.", "danger")
        return redirect(url_for('quizzes.edit', quiz_id=quiz_id))

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