import mysql.connector
import json
from datetime import datetime
from app import get_db_connection
from models.question import Question, QuestionNotFoundError

class QuizNotFoundError(Exception):
    """Exception raised when a quiz is not found"""
    pass

class Quiz:
    """Quiz model for quiz management"""
    
    def __init__(self, id, name, creator_id, created_at=None):
        self.id = id
        self.name = name
        self.creator_id = creator_id
        self.created_at = created_at or datetime.now()
    
    def to_dict(self):
        """Convert quiz to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'creator_id': self.creator_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @staticmethod
    def get_by_id(quiz_id):
        """Get quiz by ID"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT * FROM quizzes WHERE quiz_id = %s", (quiz_id,))
            quiz_data = cursor.fetchone()
            
            if not quiz_data:
                raise QuizNotFoundError(f"Quiz with ID {quiz_id} not found")
            
            created_at = quiz_data.get('created_at')
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            
            return Quiz(
                id=quiz_data['quiz_id'],
                name=quiz_data['quiz_name'],
                creator_id=quiz_data['creator_id'],
                created_at=created_at
            )
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_all():
        """Get all quizzes"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT * FROM quizzes ORDER BY created_at DESC")
            quizzes = cursor.fetchall()
            
            result = []
            for quiz_data in quizzes:
                created_at = quiz_data.get('created_at')
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                
                result.append(Quiz(
                    id=quiz_data['quiz_id'],
                    name=quiz_data['quiz_name'],
                    creator_id=quiz_data['creator_id'],
                    created_at=created_at
                ))
            
            return result
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_by_creator(creator_id):
        """Get quizzes by creator ID"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT * FROM quizzes WHERE creator_id = %s ORDER BY created_at DESC", (creator_id,))
            quizzes = cursor.fetchall()
            
            result = []
            for quiz_data in quizzes:
                created_at = quiz_data.get('created_at')
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                
                result.append(Quiz(
                    id=quiz_data['quiz_id'],
                    name=quiz_data['quiz_name'],
                    creator_id=quiz_data['creator_id'],
                    created_at=created_at
                ))
            
            return result
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def create(name, creator_id):
        """Create a new quiz"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            query = "INSERT INTO quizzes (quiz_name, creator_id) VALUES (%s, %s)"
            cursor.execute(query, (name, creator_id))
            conn.commit()
            
            # Get the inserted ID
            quiz_id = cursor.lastrowid
            
            return Quiz(
                id=quiz_id,
                name=name,
                creator_id=creator_id,
                created_at=datetime.now()
            )
        except Exception as e:
            print(f"Error creating quiz: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def update(self, name):
        """Update quiz details"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            query = "UPDATE quizzes SET quiz_name = %s WHERE quiz_id = %s"
            cursor.execute(query, (name, self.id))
            conn.commit()
            
            # Update object property
            self.name = name
            
            return True
        except Exception as e:
            print(f"Error updating quiz: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def delete(self):
        """Delete quiz and all its questions"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # First delete all questions
            query = "DELETE FROM questions WHERE quiz_id = %s"
            cursor.execute(query, (self.id,))
            
            # Then delete the quiz
            query = "DELETE FROM quizzes WHERE quiz_id = %s"
            cursor.execute(query, (self.id,))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting quiz: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_questions(self):
        """Get all questions for this quiz"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(
                "SELECT * FROM questions WHERE quiz_id = %s ORDER BY question_id ASC",
                (self.id,)
            )
            questions_data = cursor.fetchall()
            
            result = []
            for q in questions_data:
                # Parse options from JSON
                options = json.loads(q.get('options', '{}'))
                
                result.append(Question(
                    id=q['question_id'],
                    quiz_id=q['quiz_id'],
                    text=q['question_text'],
                    options=options,
                    correct_answer=q['correct_answer'],
                    score=q['score'],
                    explanation=q.get('explanation')
                ))
            
            return result
        finally:
            cursor.close()
            conn.close()
    
    def add_question(self, text, options, correct_answer, score=10, explanation=None):
        """Add a question to this quiz"""
        return Question.create(
            quiz_id=self.id,
            text=text,
            options=options,
            correct_answer=correct_answer,
            score=score,
            explanation=explanation
        )
    
    def get_scores(self, limit=None):
        """Get all scores for this quiz"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            query = """
            SELECT * FROM user_scores 
            WHERE quiz_id = %s 
            ORDER BY score DESC, timestamp ASC
            """
            
            if limit:
                query += f" LIMIT {int(limit)}"
                
            cursor.execute(query, (self.id,))
            scores = cursor.fetchall()
            
            return scores
        finally:
            cursor.close()
            conn.close()
    
    def get_user_score(self, user_id):
        """Get score for a specific user"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(
                "SELECT * FROM user_scores WHERE quiz_id = %s AND user_id = %s ORDER BY score DESC LIMIT 1",
                (self.id, user_id)
            )
            score = cursor.fetchone()
            
            return score
        finally:
            cursor.close()
            conn.close()
    
    def get_question_count(self):
        """Get the number of questions in this quiz"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM questions WHERE quiz_id = %s", (self.id,))
            count = cursor.fetchone()[0]
            
            return count
        finally:
            cursor.close()
            conn.close()
    
    def get_total_score(self):
        """Get the total possible score for this quiz"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT SUM(score) FROM questions WHERE quiz_id = %s", (self.id,))
            total = cursor.fetchone()[0]
            
            return total or 0
        finally:
            cursor.close()
            conn.close()
    
    def get_completion_count(self):
        """Get number of times this quiz has been completed"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM user_scores WHERE quiz_id = %s", (self.id,))
            count = cursor.fetchone()[0]
            
            return count
        finally:
            cursor.close()
            conn.close() 