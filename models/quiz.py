import mysql.connector
import json
from datetime import datetime
from models.db import get_db
from models.question import Question, QuestionNotFoundError
import logging

class QuizNotFoundError(Exception):
    """Exception raised when a quiz is not found"""
    pass

class Quiz:
    """Quiz model for quiz management"""
    
    def __init__(self, id, name, creator_id, created_at=None, creator_username=None):
        self.id = id
        self.name = name
        self.creator_id = creator_id
        self.created_at = created_at or datetime.now()
        self.creator_username = creator_username
    
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
        try:
            created_at_iso = None
            if self.created_at:
                try:
                    created_at_iso = self.created_at.isoformat() 
                except Exception as e:
                    # Handle case where created_at might be in an unexpected format
                    print(f"Error converting created_at to ISO format: {e}")
                    created_at_iso = str(self.created_at)
            
            return {
                'id': self.id,
                'name': self.name,
                'creator_id': self.creator_id,
                'creator_username': self.creator_username,
                'created_at': created_at_iso,
                # Include question_count if it exists
                'question_count': getattr(self, 'question_count', None)
            }
        except Exception as e:
            print(f"Error in Quiz.to_dict: {e}")
            # Provide a minimal dict as fallback
            return {
                'id': self.id,
                'name': str(self.name),
                'creator_id': str(self.creator_id)
            }
    
    @staticmethod
    def get_by_id(quiz_id):
        """Get quiz by ID"""
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM quizzes
                    WHERE quiz_id = %s
                """, (quiz_id,))
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
                    created_at=created_at,
                    creator_username=quiz_data.get('creator_username')
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
                cursor.execute("""
                    SELECT * FROM quizzes
                    ORDER BY quiz_id DESC
                """)
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
                        created_at=created_at,
                        creator_username=quiz_data.get('creator_username')
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
                cursor.execute("""
                    SELECT * FROM quizzes
                    WHERE creator_id = %s 
                    ORDER BY quiz_id DESC
                """, (creator_id,))
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
                        created_at=created_at,
                        creator_username=quiz_data.get('creator_username')
                    ))
                
                return result
        except Exception as e:
            print(f"Error getting quizzes by creator: {e}")
            # Return empty list on error rather than failing
            return []
    
    @staticmethod
    def create(name, creator_id, creator_username=None):
        """Create a new quiz"""
        try:
            # Don't import from app directly - use get_cache helper
            from flask import current_app
            import logging
            logger = logging.getLogger(__name__)
            
            conn = get_db()
            with conn.cursor() as cursor:
                # If creator_username is not provided, try to fetch it
                if creator_username is None:
                    try:
                        with conn.cursor() as user_cursor:
                            user_cursor.execute("SELECT username FROM dashboard_users WHERE discord_id = %s", (creator_id,))
                            user_data = user_cursor.fetchone()
                            if user_data:
                                creator_username = user_data['username']
                    except Exception as e:
                        logger.error(f"Error fetching username: {e}")
                        creator_username = str(creator_id)
                
                query = "INSERT INTO quizzes (quiz_name, creator_id, creator_username) VALUES (%s, %s, %s)"
                cursor.execute(query, (name, creator_id, creator_username))
                conn.commit()
                
                # Get the inserted ID
                quiz_id = cursor.lastrowid
                
                # Invalidate any user's quizzes list cache
                try:
                    cache = current_app.cache if hasattr(current_app, 'cache') else None
                    if cache:
                        # Clear cache key for this user's quiz list
                        cache_key = f"quizzes_list_{creator_id}"
                        cache.delete(cache_key)
                        logger.info(f"Invalidated cache for key: {cache_key}")
                except Exception as e:
                    logger.error(f"Error invalidating cache: {e}")
                
                return Quiz(
                    id=quiz_id,
                    name=name,
                    creator_id=creator_id,
                    created_at=datetime.now(),
                    creator_username=creator_username
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating quiz: {e}", exc_info=True)
            raise
    
    def update(self, name):
        """Update quiz details"""
        try:
            # Don't import from app directly - use get_cache helper
            from flask import current_app
            import logging
            logger = logging.getLogger(__name__)
            
            conn = get_db()
            with conn.cursor() as cursor:
                query = "UPDATE quizzes SET quiz_name = %s WHERE quiz_id = %s"
                cursor.execute(query, (name, self.id))
                conn.commit()
                
                # Update object property
                self.name = name
                
                # Invalidate caches
                try:
                    cache = current_app.cache if hasattr(current_app, 'cache') else None
                    if cache:
                        # Clear user's quiz list cache
                        cache_key = f"quizzes_list_{self.creator_id}"
                        cache.delete(cache_key)
                        logger.info(f"Invalidated creator's quiz list cache: {cache_key}")
                        
                        # Clear view cache for this quiz for all users (1-10)
                        for i in range(1, 10):
                            view_key = f"quiz_view_{self.id}_{i}"
                            cache.delete(view_key)
                        
                        # Clear preview cache
                        preview_key = f"quiz_preview_{self.id}"
                        cache.delete(preview_key)
                        logger.info(f"Invalidated quiz cache keys for quiz {self.id}")
                except Exception as e:
                    logger.error(f"Error invalidating cache: {e}")
                
                return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating quiz: {e}", exc_info=True)
            raise
    
    def delete(self):
        """Delete quiz and all its questions"""
        try:
            # Don't import from app directly - use get_cache helper
            from flask import current_app
            import logging
            logger = logging.getLogger(__name__)
            
            conn = get_db()
            with conn.cursor() as cursor:
                # First delete all questions
                query = "DELETE FROM questions WHERE quiz_id = %s"
                cursor.execute(query, (self.id,))
                
                # Then delete the quiz
                query = "DELETE FROM quizzes WHERE quiz_id = %s"
                cursor.execute(query, (self.id,))
                
                conn.commit()
                
                # Invalidate caches
                try:
                    cache = current_app.cache if hasattr(current_app, 'cache') else None
                    if cache:
                        # Clear user's quiz list cache
                        cache_key = f"quizzes_list_{self.creator_id}"
                        cache.delete(cache_key)
                        logger.info(f"Invalidated creator's quiz list cache: {cache_key}")
                        
                        # Clear view cache for this quiz for all users (1-10)
                        for i in range(1, 10):
                            view_key = f"quiz_view_{self.id}_{i}"
                            cache.delete(view_key)
                        
                        # Clear preview cache
                        preview_key = f"quiz_preview_{self.id}"
                        cache.delete(preview_key)
                        logger.info(f"Invalidated quiz cache keys for quiz {self.id}")
                except Exception as e:
                    logger.error(f"Error invalidating cache: {e}")
                
                return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting quiz: {e}", exc_info=True)
            raise
    
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
    
    @staticmethod
    def from_dict(data):
        """Create a Quiz object from a dictionary (for deserialization from cache)"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            created_at = data.get('created_at')
            if created_at and isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except ValueError as e:
                    logger.warning(f"Could not parse datetime string: {created_at}, error: {e}")
                    created_at = datetime.now()
            
            # Ensure all required fields exist with fallbacks
            quiz_id = data.get('id')
            if not quiz_id:
                raise ValueError("Quiz dictionary missing required 'id' field")
                
            return Quiz(
                id=quiz_id,
                name=data.get('name', 'Unnamed Quiz'),
                creator_id=data.get('creator_id', 0),
                created_at=created_at,
                creator_username=data.get('creator_username', 'Unknown')
            )
        except Exception as e:
            logger.error(f"Error deserializing quiz from dictionary: {e}", exc_info=True)
            raise
        
    @staticmethod
    def question_from_dict(data):
        """Create a Question object from a dictionary (for deserialization from cache)"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Ensure all required fields exist with fallbacks
            question_id = data.get('id')
            quiz_id = data.get('quiz_id')
            
            if not question_id or not quiz_id:
                logger.error(f"Question dictionary missing required fields: {data}")
                raise ValueError("Question dictionary missing required fields: 'id' or 'quiz_id'")
            
            # Ensure options is a dictionary
            options = data.get('options', {})
            if not isinstance(options, dict):
                logger.warning(f"Question options is not a dictionary, converting: {options}")
                if isinstance(options, str):
                    try:
                        import json
                        options = json.loads(options)
                    except:
                        options = {}
                else:
                    options = {}
            
            return Question(
                id=question_id,
                quiz_id=quiz_id,
                text=data.get('text', 'No question text'),
                options=options,
                correct_answer=data.get('correct_answer', ''),
                score=data.get('score', 10),
                explanation=data.get('explanation', '')
            )
        except Exception as e:
            logger.error(f"Error deserializing question from dictionary: {e}", exc_info=True)
            raise 