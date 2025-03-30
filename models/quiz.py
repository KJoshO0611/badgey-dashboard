import mysql.connector
import json
from datetime import datetime
from models.db import get_db
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
    
    @property
    def quiz_id(self):
        """For backwards compatibility with templates using quiz.quiz_id"""
        return self.id
    
    @property
    def quiz_name(self):
        """For backwards compatibility with templates using quiz.quiz_name"""
        return self.name
    
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
        conn = get_db()
        try:
            with conn.cursor() as cursor:
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
        except Exception as e:
            if isinstance(e, QuizNotFoundError):
                raise e
            print(f"Error getting quiz: {e}")
            raise e
    
    @staticmethod
    def get_all():
        """Get all quizzes"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM quizzes ORDER BY quiz_id DESC")
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
        except Exception as e:
            print(f"Error getting all quizzes: {e}")
            # Return empty list on error rather than failing
            return []
    
    @staticmethod
    def get_by_creator(creator_id):
        """Get quizzes by creator ID"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM quizzes WHERE creator_id = %s ORDER BY quiz_id DESC", (creator_id,))
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
        except Exception as e:
            print(f"Error getting quizzes by creator: {e}")
            # Return empty list on error rather than failing
            return []
    
    @staticmethod
    def create(name, creator_id):
        """Create a new quiz"""
        conn = get_db()
        with conn.cursor() as cursor:
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
    
    def update(self, name):
        """Update quiz details"""
        conn = get_db()
        with conn.cursor() as cursor:
            query = "UPDATE quizzes SET quiz_name = %s WHERE quiz_id = %s"
            cursor.execute(query, (name, self.id))
            conn.commit()
            
            # Update object property
            self.name = name
            
            return True
    
    def delete(self):
        """Delete quiz and all its questions"""
        conn = get_db()
        with conn.cursor() as cursor:
            # First delete all questions
            query = "DELETE FROM questions WHERE quiz_id = %s"
            cursor.execute(query, (self.id,))
            
            # Then delete the quiz
            query = "DELETE FROM quizzes WHERE quiz_id = %s"
            cursor.execute(query, (self.id,))
            
            conn.commit()
            return True
    
    def get_questions(self):
        """Get all questions for this quiz"""
        conn = get_db()
        with conn.cursor() as cursor:
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
        conn = get_db()
        with conn.cursor() as cursor:
            query = """
            SELECT * FROM user_scores 
            WHERE quiz_id = %s 
            ORDER BY score DESC, completed_at ASC
            """
            
            if limit:
                query += f" LIMIT {int(limit)}"
                
            cursor.execute(query, (self.id,))
            scores = cursor.fetchall()
            
            return scores
    
    def get_user_score(self, user_id):
        """Get score for a specific user"""
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM user_scores WHERE quiz_id = %s AND user_id = %s ORDER BY score DESC LIMIT 1",
                (self.id, user_id)
            )
            score = cursor.fetchone()
            
            return score
    
    def get_question_count(self):
        """Get the number of questions in this quiz"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM questions WHERE quiz_id = %s", (self.id,))
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            print(f"Error getting question count: {e}")
            return 0
    
    def get_total_score(self):
        """Get the total possible score for this quiz"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT SUM(score) as total FROM questions WHERE quiz_id = %s", (self.id,))
                result = cursor.fetchone()
                return result['total'] or 0
        except Exception as e:
            print(f"Error getting total score: {e}")
            return 0
    
    def get_completion_count(self):
        """Get number of times this quiz has been completed"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM user_scores WHERE quiz_id = %s", (self.id,))
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            print(f"Error getting completion count: {e}")
            return 0 