import mysql.connector
import json
from app import get_db_connection

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
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT * FROM questions WHERE question_id = %s", (question_id,))
            q = cursor.fetchone()
            
            if not q:
                raise QuestionNotFoundError(f"Question with ID {question_id} not found")
            
            # Parse options from JSON
            options = json.loads(q.get('options', '{}'))
            
            return Question(
                id=q['question_id'],
                quiz_id=q['quiz_id'],
                text=q['question_text'],
                options=options,
                correct_answer=q['correct_answer'],
                score=q['score'],
                explanation=q.get('explanation')
            )
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def create(quiz_id, text, options, correct_answer, score=10, explanation=None):
        """Create a new question"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Ensure options is in JSON format
            if isinstance(options, dict):
                options_json = json.dumps(options)
            else:
                options_json = options
            
            query = """
            INSERT INTO questions 
            (quiz_id, question_text, options, correct_answer, score, explanation) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (quiz_id, text, options_json, correct_answer, score, explanation))
            conn.commit()
            
            # Get the inserted ID
            question_id = cursor.lastrowid
            
            return Question(
                id=question_id,
                quiz_id=quiz_id,
                text=text,
                options=options,
                correct_answer=correct_answer,
                score=score,
                explanation=explanation
            )
        except Exception as e:
            print(f"Error creating question: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def update(self, text=None, options=None, correct_answer=None, score=None, explanation=None):
        """Update question details"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Build query dynamically based on provided parameters
            update_parts = []
            params = []
            
            if text is not None:
                update_parts.append("question_text = %s")
                params.append(text)
                self.text = text
            
            if options is not None:
                # Ensure options is in JSON format
                if isinstance(options, dict):
                    options_json = json.dumps(options)
                else:
                    options_json = options
                
                update_parts.append("options = %s")
                params.append(options_json)
                self.options = options if isinstance(options, dict) else json.loads(options)
            
            if correct_answer is not None:
                update_parts.append("correct_answer = %s")
                params.append(correct_answer)
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
            return False
        finally:
            cursor.close()
            conn.close()
    
    def delete(self):
        """Delete the question"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            query = "DELETE FROM questions WHERE question_id = %s"
            cursor.execute(query, (self.id,))
            conn.commit()
            
            return True
        except Exception as e:
            print(f"Error deleting question: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_option_text(question_id, option_key):
        """Get text for a specific option"""
        question = Question.get_by_id(question_id)
        return question.options.get(option_key, '')
    
    def get_correct_option_text(self):
        """Get text for the correct option"""
        return self.options.get(self.correct_answer, '') 