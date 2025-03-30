import mysql.connector
import json
from models.db import get_db

class QuestionNotFoundError(Exception):
    """Exception raised when a question is not found"""
    pass

class Question:
    """Question model for question management"""
    
    def __init__(self, id, quiz_id, text, options, correct_answer, score=10, explanation=None):
        self.id = id
        self.quiz_id = quiz_id
        self.text = text
        self.options = options if isinstance(options, dict) else json.loads(options)
        self.correct_answer = correct_answer
        self.score = score
        self.explanation = explanation
    
    def to_dict(self):
        """Convert question to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'quiz_id': self.quiz_id,
            'text': self.text,
            'options': self.options,
            'correct_answer': self.correct_answer,
            'score': self.score,
            'explanation': self.explanation
        }
    
    @staticmethod
    def get_by_id(question_id):
        """Get question by ID"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM questions WHERE question_id = %s", (question_id,))
                q = cursor.fetchone()
                
                if not q:
                    raise QuestionNotFoundError(f"Question with ID {question_id} not found")
                
                # Parse options from JSON
                options = q.get('options', '[]')
                if isinstance(options, str):
                    options = options.split('|')
                
                return Question(
                    id=q['question_id'],
                    quiz_id=q['quiz_id'],
                    text=q['question'],
                    options=options,
                    correct_answer=q['correct_answer'],
                    score=q['score'],
                    explanation=q.get('explanation')
                )
        except Exception as e:
            if isinstance(e, QuestionNotFoundError):
                raise e
            print(f"Error getting question: {e}")
            raise e
    
    @classmethod
    def create(cls, quiz_id, text, options, correct_answer, score=10, explanation=None):
        """Create a new question for a quiz."""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                # Ensure options is a JSON string
                if isinstance(options, dict):
                    options_json = json.dumps(options)
                elif isinstance(options, str):
                    # If it's already a string, make sure it's valid JSON
                    try:
                        json.loads(options)
                        options_json = options
                    except:
                        # If not valid JSON, assume it's a string representation that needs conversion
                        options_json = json.dumps(options)
                else:
                    options_json = json.dumps(options)
                
                # Create the question
                cursor.execute(
                    "INSERT INTO questions (quiz_id, question_text, options, correct_answer, score, explanation) VALUES (%s, %s, %s, %s, %s, %s)",
                    (quiz_id, text, options_json, str(correct_answer), score, explanation)
                )
                conn.commit()
                
                # Get the ID of the new question
                question_id = cursor.lastrowid
                
                return cls(question_id, quiz_id, text, options, correct_answer, score, explanation)
        except Exception as e:
            conn.rollback()
            raise e
    
    def update(self, text=None, options=None, correct_answer=None, score=None, explanation=None):
        """Update question details"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                # Build query dynamically based on provided parameters
                update_parts = []
                params = []
                
                if text is not None:
                    update_parts.append("question_text = %s")
                    params.append(text)
                    self.text = text
                
                if options is not None:
                    # Ensure options is properly formatted for the database with lettered keys
                    formatted_options = {}
                    
                    # Convert array to lettered format if needed
                    if isinstance(options, list):
                        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
                        for i, option in enumerate(options):
                            if i < len(letters):
                                formatted_options[letters[i]] = option
                    # If already a dict with lettered keys, use as is
                    elif isinstance(options, dict):
                        formatted_options = options
                    # If string, convert to dict (assuming it's already in JSON format)
                    elif isinstance(options, str):
                        try:
                            formatted_options = json.loads(options)
                        except:
                            # If not valid JSON, create a single option
                            formatted_options = {"A": options}
                    else:
                        formatted_options = {}
                    
                    # Convert to JSON string
                    options_json = json.dumps(formatted_options)
                    
                    update_parts.append("options = %s")
                    params.append(options_json)
                    self.options = formatted_options
                
                if correct_answer is not None:
                    update_parts.append("correct_answer = %s")
                    params.append(str(correct_answer))
                    self.correct_answer = correct_answer
                
                if score is not None:
                    update_parts.append("score = %s")
                    params.append(score)
                    self.score = score
                
                if explanation is not None:
                    update_parts.append("explanation = %s")
                    params.append(explanation)
                    self.explanation = explanation
                
                if not update_parts:
                    # Nothing to update
                    return True
                
                # Add question_id parameter
                params.append(self.id)
                
                query = f"UPDATE questions SET {', '.join(update_parts)} WHERE question_id = %s"
                cursor.execute(query, params)
                conn.commit()
                
                return True
        except Exception as e:
            print(f"Error updating question: {e}")
            conn.rollback()
            return False
    
    def delete(self):
        """Delete the question"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                query = "DELETE FROM questions WHERE question_id = %s"
                cursor.execute(query, (self.id,))
                conn.commit()
                
                return True
        except Exception as e:
            print(f"Error deleting question: {e}")
            return False
    
    @staticmethod
    def get_option_text(question_id, option_key):
        """Get text for a specific option"""
        question = Question.get_by_id(question_id)
        return question.options.get(option_key, '')
    
    def get_correct_option_text(self):
        """Get text for the correct option"""
        return self.options.get(self.correct_answer, '') 