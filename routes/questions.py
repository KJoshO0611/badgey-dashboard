from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from flask_login import login_required, current_user
import json
from models.quiz import Quiz, QuizNotFoundError
from models.question import Question, QuestionNotFoundError
from decorators import role_required

questions_bp = Blueprint('questions', __name__, url_prefix='/questions')

@questions_bp.route('/create/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
@role_required(['quiz_creator', 'admin'])
def create(quiz_id):
    """Create a new question for a quiz"""
    try:
        quiz = Quiz.get_by_id(quiz_id)
        
        # Check if user has permission to edit this quiz
        if quiz.creator_id != current_user.discord_id and not current_user.has_role('admin'):
            flash('You do not have permission to add questions to this quiz', 'error')
            return redirect(url_for('quizzes.view', quiz_id=quiz_id))
        
        if request.method == 'POST':
            question_text = request.form.get('question_text')
            options_data = {}
            
            # Parse options
            for key in request.form:
                if key.startswith('option_key_'):
                    index = key.replace('option_key_', '')
                    option_key = request.form.get(key)
                    option_value = request.form.get(f'option_value_{index}')
                    
                    if option_key and option_value:
                        options_data[option_key] = option_value
            
            correct_answer = request.form.get('correct_answer')
            score = int(request.form.get('score', 10))
            explanation = request.form.get('explanation')
            
            # Validate inputs
            if not question_text:
                flash('Question text is required', 'error')
            elif not options_data:
                flash('At least one option is required', 'error')
            elif not correct_answer:
                flash('Correct answer is required', 'error')
            elif correct_answer not in options_data:
                flash('Correct answer must be one of the options', 'error')
            else:
                # Create question
                question = quiz.add_question(
                    text=question_text,
                    options=options_data,
                    correct_answer=correct_answer,
                    score=score,
                    explanation=explanation
                )
                
                if question:
                    flash('Question added successfully', 'success')
                    return redirect(url_for('quizzes.edit', quiz_id=quiz_id))
                else:
                    flash('Failed to add question', 'error')
        
        return render_template('questions/create.html', quiz=quiz)
    
    except QuizNotFoundError:
        flash('Quiz not found', 'error')
        return redirect(url_for('quizzes.list_quizzes'))

@questions_bp.route('/edit/<int:question_id>', methods=['GET', 'POST'])
@login_required
def edit(question_id):
    """Edit an existing question"""
    try:
        question = Question.get_by_id(question_id)
        quiz = Quiz.get_by_id(question.quiz_id)
        
        # Check if user has permission to edit
        if quiz.creator_id != current_user.discord_id and not current_user.has_role('admin'):
            flash('You do not have permission to edit this question', 'error')
            return redirect(url_for('quizzes.view', quiz_id=quiz.id))
        
        if request.method == 'POST':
            question_text = request.form.get('question_text')
            options_data = {}
            
            # Parse options
            for key in request.form:
                if key.startswith('option_key_'):
                    index = key.replace('option_key_', '')
                    option_key = request.form.get(key)
                    option_value = request.form.get(f'option_value_{index}')
                    
                    if option_key and option_value:
                        options_data[option_key] = option_value
            
            correct_answer = request.form.get('correct_answer')
            score = int(request.form.get('score', 10))
            explanation = request.form.get('explanation')
            
            # Validate inputs
            if not question_text:
                flash('Question text is required', 'error')
            elif not options_data:
                flash('At least one option is required', 'error')
            elif not correct_answer:
                flash('Correct answer is required', 'error')
            elif correct_answer not in options_data:
                flash('Correct answer must be one of the options', 'error')
            else:
                # Update question
                success = question.update(
                    text=question_text,
                    options=options_data,
                    correct_answer=correct_answer,
                    score=score,
                    explanation=explanation
                )
                
                if success:
                    flash('Question updated successfully', 'success')
                    return redirect(url_for('quizzes.edit', quiz_id=quiz.id))
                else:
                    flash('Failed to update question', 'error')
        
        return render_template('questions/edit.html', question=question, quiz=quiz)
    
    except QuestionNotFoundError:
        flash('Question not found', 'error')
        return redirect(url_for('quizzes.list_quizzes'))
    except QuizNotFoundError:
        flash('Quiz not found', 'error')
        return redirect(url_for('quizzes.list_quizzes'))

@questions_bp.route('/delete/<int:question_id>', methods=['POST'])
@login_required
def delete(question_id):
    """Delete a question"""
    try:
        question = Question.get_by_id(question_id)
        quiz = Quiz.get_by_id(question.quiz_id)
        
        # Check if user has permission to delete
        if quiz.creator_id != current_user.discord_id and not current_user.has_role('admin'):
            flash('You do not have permission to delete this question', 'error')
            return redirect(url_for('quizzes.view', quiz_id=quiz.id))
        
        success = question.delete()
        
        if success:
            flash('Question deleted successfully', 'success')
        else:
            flash('Failed to delete question', 'error')
        
        return redirect(url_for('quizzes.edit', quiz_id=quiz.id))
    
    except QuestionNotFoundError:
        flash('Question not found', 'error')
        return redirect(url_for('quizzes.list_quizzes'))
    except QuizNotFoundError:
        flash('Quiz not found', 'error')
        return redirect(url_for('quizzes.list_quizzes'))

# API Endpoints for AJAX
@questions_bp.route('/api/<int:question_id>')
@login_required
def api_get_question(question_id):
    """API endpoint to get question details"""
    try:
        question = Question.get_by_id(question_id)
        return jsonify(question.to_dict())
    
    except QuestionNotFoundError:
        return jsonify({'error': 'Question not found'}), 404

@questions_bp.route('/api/quiz/<int:quiz_id>')
@login_required
def api_get_quiz_questions(quiz_id):
    """API endpoint to get all questions for a quiz"""
    try:
        quiz = Quiz.get_by_id(quiz_id)
        questions = quiz.get_questions()
        
        return jsonify([q.to_dict() for q in questions])
    
    except QuizNotFoundError:
        return jsonify({'error': 'Quiz not found'}), 404 