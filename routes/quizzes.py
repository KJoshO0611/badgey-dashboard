import logging
from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from flask_login import login_required, current_user
import json
import pickle
from models.quiz import Quiz, QuizNotFoundError
from decorators import role_required
from models.db import get_db
from flask import current_app

logger = logging.getLogger(__name__)

quizzes_bp = Blueprint('quizzes', __name__, url_prefix='/quizzes')

def serialize_quiz_data(quizzes):
    """Serialize quiz data for caching."""
    try:
        if isinstance(quizzes, list):
            # Return a list of dictionaries
            return [quiz.to_dict() for quiz in quizzes]
        else:
            # Return a single dictionary
            return quizzes.to_dict()
    except Exception as e:
        logger.error(f"Error in serialize_quiz_data: {e}")
        raise

def deserialize_quiz_data(data, is_list=True):
    """Deserialize quiz data from cache."""
    try:
        if is_list:
            # Convert list of dicts to list of Quiz objects
            return [Quiz.from_dict(quiz_dict) for quiz_dict in data]
        else:
            # Convert dict to Quiz object
            return Quiz.from_dict(data)
    except Exception as e:
        logger.error(f"Error in deserialize_quiz_data: {e}")
        raise

@quizzes_bp.route('/')
@login_required
def list():
    """List all quizzes for the current user."""
    try:
        logger.info("Fetching quizzes for list view")
        
        # Get the cache object directly from the app
        cache = None
        if hasattr(current_app, 'extensions') and 'cache' in current_app.extensions:
            cache = current_app.extensions['cache']
            logger.info("Cache extension found")
        else:
            logger.warning("Cache extension not found in current_app.extensions")
            logger.debug(f"Available extensions: {list(current_app.extensions.keys()) if hasattr(current_app, 'extensions') else 'none'}")
        
        # Get quizzes based on user role - do this first in case cache fails
        if current_user.has_role('admin'):
            logger.info("Admin user: fetching all quizzes")
            quizzes = Quiz.get_all()
        else:
            logger.info(f"Regular user: fetching quizzes for user {current_user.discord_id}")
            quizzes = Quiz.get_by_creator(current_user.discord_id)
        
        # Add question counts to each quiz
        for quiz in quizzes:
            quiz.question_count = quiz.get_question_count()
        
        # Try to get quizzes from cache first - with detailed error handling
        try:
            cache_key = f"quizzes_list_{current_user.id}"
            if cache and hasattr(cache, 'get'):
                logger.info(f"Attempting to get cached quizzes with key: {cache_key}")
                try:
                    cached_data = cache.get(cache_key)
                    if cached_data:
                        logger.info(f"Using cached quizzes for user {current_user.id}")
                        cached_quizzes = deserialize_quiz_data(cached_data)
                        return render_template('quizzes/list.html', quizzes=cached_quizzes)
                    else:
                        logger.info(f"No cached data found for key: {cache_key}")
                except Exception as cache_get_error:
                    logger.error(f"Error getting data from cache: {cache_get_error}", exc_info=True)
            else:
                logger.warning("Cache object not available or doesn't have get method")
                
            # Cache the results for 5 minutes
            if cache and hasattr(cache, 'set'):
                try:
                    logger.info(f"Attempting to cache quizzes with key: {cache_key}")
                    serialized_data = serialize_quiz_data(quizzes)
                    cache.set(cache_key, serialized_data, timeout=300)
                    logger.info(f"Cached quizzes for user {current_user.id}")
                except Exception as cache_set_error:
                    logger.warning(f"Failed to cache quizzes: {cache_set_error}")
                    logger.error("Cache error details", exc_info=True)
        except Exception as cache_error:
            logger.error(f"General caching error: {cache_error}", exc_info=True)
            # Continue with non-cached quizzes
        
        return render_template('quizzes/list.html', quizzes=quizzes)
    except Exception as e:
        logger.error(f"Error listing quizzes: {e}", exc_info=True)
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
        # Fetch the quiz directly first to ensure we have a fallback
        logger.info(f"Fetching quiz with ID {quiz_id} for viewing")
        quiz = Quiz.get_by_id(quiz_id)
        
        # Check if user has permission to view this quiz
        if not current_user.has_role('admin') and quiz.creator_id != current_user.discord_id:
            logger.warning(f"User {current_user.discord_id} attempted to view quiz {quiz_id} without permission")
            flash("You don't have permission to view this quiz.", "danger")
            return redirect(url_for('quizzes.list'))
        
        logger.info(f"Fetching questions for quiz {quiz_id}")
        questions = quiz.get_questions()
        
        # Check cache with robust error handling
        try:
            cache = None
            if hasattr(current_app, 'extensions') and 'cache' in current_app.extensions:
                cache = current_app.extensions['cache']
                logger.info("Cache extension found for quiz view")
            else:
                logger.warning("Cache extension not found in current_app.extensions for quiz view")
                
            cache_key = f"quiz_view_{quiz_id}_{current_user.id}"
            
            if cache and hasattr(cache, 'get'):
                try:
                    logger.info(f"Attempting to get cached quiz data with key: {cache_key}")
                    cached_data = cache.get(cache_key)
                    if cached_data:
                        logger.info(f"Using cached quiz data for quiz {quiz_id}")
                        quiz_data, questions_data = cached_data
                        cached_quiz = deserialize_quiz_data(quiz_data, is_list=False)
                        cached_questions = [Quiz.question_from_dict(q) for q in questions_data]
                        return render_template('quizzes/view.html', quiz=cached_quiz, questions=cached_questions)
                    else:
                        logger.info(f"No cached data found for quiz {quiz_id}")
                except Exception as cache_get_error:
                    logger.error(f"Error getting data from cache: {cache_get_error}", exc_info=True)
                    
            # Cache the results
            if cache and hasattr(cache, 'set'):
                try:
                    logger.info(f"Attempting to cache quiz data with key: {cache_key}")
                    quiz_data = serialize_quiz_data(quiz)
                    questions_data = [q.to_dict() for q in questions]
                    cache.set(cache_key, (quiz_data, questions_data), timeout=300)
                    logger.info(f"Cached quiz data for quiz {quiz_id}")
                except Exception as cache_set_error:
                    logger.warning(f"Failed to cache quiz data: {cache_set_error}")
                    logger.error("Cache error details", exc_info=True)
        except Exception as cache_error:
            logger.error(f"General caching error: {cache_error}", exc_info=True)
            # Continue with non-cached quiz data
                
        return render_template('quizzes/view.html', quiz=quiz, questions=questions)
    except Exception as e:
        logger.error(f"Error viewing quiz: {e}", exc_info=True)
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
        # Fetch quiz data directly first as fallback
        logger.info(f"Fetching quiz with ID {quiz_id} for preview")
        quiz = Quiz.get_by_id(quiz_id)
        
        logger.info(f"Fetching questions for quiz {quiz_id}")
        questions = quiz.get_questions()
        
        # Check cache with robust error handling
        try:
            cache = None
            if hasattr(current_app, 'extensions') and 'cache' in current_app.extensions:
                cache = current_app.extensions['cache']
                logger.info("Cache extension found for quiz preview")
            else:
                logger.warning("Cache extension not found in current_app.extensions for quiz preview")
                
            cache_key = f"quiz_preview_{quiz_id}"
            
            if cache and hasattr(cache, 'get'):
                try:
                    logger.info(f"Attempting to get cached preview data with key: {cache_key}")
                    cached_data = cache.get(cache_key)
                    if cached_data:
                        logger.info(f"Using cached preview data for quiz {quiz_id}")
                        quiz_data, questions_data = cached_data
                        cached_quiz = deserialize_quiz_data(quiz_data, is_list=False)
                        cached_questions = [Quiz.question_from_dict(q) for q in questions_data]
                        return render_template('quizzes/preview.html', quiz=cached_quiz, questions=cached_questions)
                    else:
                        logger.info(f"No cached preview data found for quiz {quiz_id}")
                except Exception as cache_get_error:
                    logger.error(f"Error getting preview data from cache: {cache_get_error}", exc_info=True)
                    
            # Cache the results
            if cache and hasattr(cache, 'set'):
                try:
                    logger.info(f"Attempting to cache preview data with key: {cache_key}")
                    quiz_data = serialize_quiz_data(quiz)
                    questions_data = [q.to_dict() for q in questions]
                    cache.set(cache_key, (quiz_data, questions_data), timeout=300)
                    logger.info(f"Cached preview data for quiz {quiz_id}")
                except Exception as cache_set_error:
                    logger.warning(f"Failed to cache preview data: {cache_set_error}")
                    logger.error("Cache error details", exc_info=True)
        except Exception as cache_error:
            logger.error(f"General caching error in preview: {cache_error}", exc_info=True)
            # Continue with non-cached quiz data
        
        return render_template('quizzes/preview.html', quiz=quiz, questions=questions)
    
    except QuizNotFoundError:
        logger.error(f"Quiz with ID {quiz_id} not found")
        flash('Quiz not found', 'error')
        return redirect(url_for('quizzes.list'))
    except Exception as e:
        logger.error(f"Error previewing quiz {quiz_id}: {e}", exc_info=True)
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
        
        # Extract the options from the form
        options = {}
        correct_answer = request.form.get('correct_answer')
        
        # Build options dictionary with letter keys
        for key, value in request.form.items():
            if key.startswith('option') and len(key) > 6:
                letter = key[6:]  # Extract the letter (A, B, C, etc.)
                if value.strip():  # Only add non-empty options
                    options[letter] = value.strip()
        
        # Get correct answer and score
        score = request.form.get('score', 10)
        explanation = request.form.get('explanation', '')
        
        # Validate inputs
        if not question_text:
            flash('Question text is required', 'danger')
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        if len(options) < 2:
            flash('At least two options are required', 'danger')
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        if not correct_answer or correct_answer not in options:
            flash('A valid correct answer must be selected', 'danger')
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        if not score or int(score) < 1:
            flash('Score must be at least 1 point', 'danger')
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
        
        # Extract the options from the form
        options = {}
        correct_answer = request.form.get('correct_answer')
        
        # Build options dictionary with letter keys
        for key, value in request.form.items():
            if key.startswith('option') and len(key) > 6:
                letter = key[6:]  # Extract the letter (A, B, C, etc.)
                if value.strip():  # Only add non-empty options
                    options[letter] = value.strip()
        
        # Get correct answer and score
        score = request.form.get('score', 10)
        explanation = request.form.get('explanation', '')
        
        # Validate inputs
        if not question_text:
            flash('Question text is required', 'danger')
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        if len(options) < 2:
            flash('At least two options are required', 'danger')
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        if not correct_answer or correct_answer not in options:
            flash('A valid correct answer must be selected', 'danger')
            return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
        
        if not score or int(score) < 1:
            flash('Score must be at least 1 point', 'danger')
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