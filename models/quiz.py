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

    @staticmethod
    def get_all_question_counts():
        """Return a dict mapping quiz_id to question count for all quizzes."""
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT quiz_id, COUNT(*) as count FROM questions GROUP BY quiz_id")
            rows = cursor.fetchall()
            return {row['quiz_id']: row['count'] for row in rows}

    @staticmethod
    def get_all_total_scores():
        """Return a dict mapping quiz_id to total score for all quizzes."""
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT quiz_id, SUM(score) as total FROM questions GROUP BY quiz_id")
            rows = cursor.fetchall()
            return {row['quiz_id']: int(row['total']) if row['total'] is not None else 0 for row in rows}
    
    def __init__(self, id, name, creator_id, created_at=None, creator_username=None, question_limit=None):
        self.id = id
        self.name = name
        self.creator_id = creator_id
        self.created_at = created_at or datetime.now()
        self.creator_username = creator_username
        self.question_limit = question_limit

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
            quiz_id = data.get('id')
            if not quiz_id:
                raise ValueError("Quiz dictionary missing required 'id' field")
            quiz = Quiz(
                id=quiz_id,
                name=data.get('name', 'Unnamed Quiz'),
                creator_id=data.get('creator_id', 0),
                created_at=created_at,
                creator_username=data.get('creator_username', 'Unknown'),
                question_limit=data.get('question_limit')
            )
            if 'question_count' in data:
                quiz.question_count = data['question_count']
            if 'total_points' in data:
                quiz.total_points = data['total_points']
            return quiz
        except Exception as e:
            logger.error(f"Error deserializing quiz from dictionary: {e}", exc_info=True)
            raise

        self.id = id
        self.name = name
        self.creator_id = creator_id
        self.created_at = created_at or datetime.now()
        self.creator_username = creator_username
        self.question_limit = question_limit
        self.total_points = total_points
        self.start_date = start_date
        self.end_date = end_date
    
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
            
            # Ensure question_count and total_points are int for JSON serialization
            question_count = getattr(self, 'question_count', None)
            total_points = getattr(self, 'total_points', None)
            if question_count is not None:
                try:
                    question_count = int(question_count)
                except Exception:
                    pass
            if total_points is not None:
                try:
                    total_points = int(total_points)
                except Exception:
                    pass
            return {
                'id': self.id,
                'name': self.name,
                'creator_id': self.creator_id,
                'creator_username': self.creator_username,
                'created_at': created_at_iso,
                'question_limit': self.question_limit,
                'question_count': question_count,
                'total_points': total_points
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
                    creator_username=quiz_data.get('creator_username'),
                    question_limit=quiz_data.get('question_limit'),
                    start_date=quiz_data.get('start_date'),
                    end_date=quiz_data.get('end_date')
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
                        creator_username=quiz_data.get('creator_username'),
                        question_limit=quiz_data.get('question_limit')
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
                        creator_username=quiz_data.get('creator_username'),
                        question_limit=quiz_data.get('question_limit')
                    ))
                
                return result
        except Exception as e:
            print(f"Error getting quizzes by creator: {e}")
            # Return empty list on error rather than failing
            return []
    
    @staticmethod
    def create(name, creator_id, creator_username=None, question_limit=None, start_date=None, end_date=None):
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
                
                query = "INSERT INTO quizzes (quiz_name, creator_id, creator_username, question_limit, start_date, end_date) VALUES (%s, %s, %s, %s, %s, %s)"
                cursor.execute(query, (name, creator_id, creator_username, question_limit, start_date, end_date))
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
                    creator_username=creator_username,
                    question_limit=question_limit,
                    start_date=start_date,
                    end_date=end_date
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating quiz: {e}", exc_info=True)
            raise
    
    def update(self, name, question_limit=None, start_date=None, end_date=None):
        """Update quiz details, including start and end date"""
        try:
            # Don't import from app directly - use get_cache helper
            from flask import current_app
            import logging
            logger = logging.getLogger(__name__)
            
            conn = get_db()
            with conn.cursor() as cursor:
                query = "UPDATE quizzes SET quiz_name = %s, question_limit = %s, start_date = %s, end_date = %s WHERE quiz_id = %s"
                cursor.execute(query, (name, question_limit, start_date, end_date, self.id))
                conn.commit()
                
                # Update object property
                self.name = name
                self.question_limit = question_limit
                self.start_date = start_date
                self.end_date = end_date
                
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

    # End of previous method

    # The following methods are part of the Quiz class

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
                correct_answer=q.get('correct_answer', ''),
                score=q.get('score', 10),
                explanation=q.get('explanation', '')
            ))
    return result