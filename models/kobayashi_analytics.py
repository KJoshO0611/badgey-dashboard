from models.db import get_db
import json

def get_story_run_stats():
    """Get statistics about story runs for analytics"""
    conn = get_db()
    story_stats = []
    
    with conn.cursor() as cursor:
        # Get total runs and participations per story using player_choices table
        cursor.execute("""
            SELECT 
                s.id,
                s.title,
                COUNT(DISTINCT pc.run_id) as total_runs,
                COUNT(DISTINCT pc.user_id) as unique_users
            FROM 
                stories s
            LEFT JOIN 
                player_choices pc ON SUBSTRING_INDEX(pc.run_id, '_', 1) = s.code
            GROUP BY 
                s.id, s.title
            ORDER BY 
                total_runs DESC
        """)
        base_stats = cursor.fetchall()
        
        # Add estimated completion rate based on points earned
        story_stats = []
        for story in base_stats:
            # Fetch all runs for this story to calculate completion rate
            story_code = None
            if story['id'] == 2:
                story_code = 'TITEN'
            elif story['id'] == 3:
                story_code = 'KHAN'
                
            if story_code:
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT run_id) as total_runs,
                        COUNT(DISTINCT CASE WHEN points >= 10 THEN run_id END) as completed_runs
                    FROM 
                        user_points
                    WHERE 
                        run_id LIKE %s
                """, (f"{story_code}_%",))
                completion_data = cursor.fetchone()
                
                # Add completion data to story stats
                story_stats.append({
                    'id': story['id'],
                    'title': story['title'],
                    'total_runs': story['total_runs'] or 0,
                    'completions': completion_data['completed_runs'] if completion_data else 0,
                    'unique_users': story['unique_users'] or 0
                })
            else:
                # For stories without completion data, use defaults
                story_stats.append({
                    'id': story['id'],
                    'title': story['title'],
                    'total_runs': story['total_runs'] or 0,
                    'completions': 0,
                    'unique_users': story['unique_users'] or 0
                })
    
    return story_stats

def get_choice_distribution(story_id=None):
    """Get distribution of choices made across all stories or a specific story"""
    conn = get_db()
    choice_stats = []
    
    with conn.cursor() as cursor:
        # Build the query with optional story_id filter
        query = """
            SELECT 
                sn.story_id,
                s.title as story_title,
                sn.id as node_id,
                sn.title as node_title,
                pc.choice as choice_key,
                COUNT(*) as choice_count
            FROM 
                player_choices pc
            JOIN 
                story_nodes sn ON pc.node_id = sn.id
            JOIN 
                stories s ON sn.story_id = s.id
        """
        
        params = []
        if story_id:
            query += " WHERE sn.story_id = %s"
            params.append(story_id)
        
        query += """
            GROUP BY 
                sn.story_id, s.title, sn.id, sn.title, pc.choice
            ORDER BY 
                choice_count DESC
            LIMIT 20
        """
        
        cursor.execute(query, tuple(params))
        choice_data = cursor.fetchall()
        
        # For each choice, get the choice text based on the choice key
        for row in choice_data:
            choice_key = row['choice_key']
            # Make the choice more readable
            choice_text = choice_key.replace('_', ' ').capitalize()
            
            choice_stats.append({
                'story_id': row['story_id'],
                'story_title': row['story_title'],
                'node_id': row['node_id'],
                'node_title': row['node_title'],
                'choice_key': choice_key,
                'choice_text': choice_text,
                'choice_count': row['choice_count']
            })
    
    return choice_stats

def get_user_participation():
    """Get user participation stats"""
    conn = get_db()
    user_stats = []
    
    with conn.cursor() as cursor:
        # Get user participation data using player_choices and user_points tables
        # Join with members table to get actual usernames
        cursor.execute("""
            SELECT 
                pc.user_id,
                m.user_name,
                COUNT(DISTINCT pc.run_id) as total_runs,
                COUNT(DISTINCT SUBSTRING_INDEX(pc.run_id, '_', 1)) as stories_played,
                MAX(pc.timestamp) as last_played
            FROM 
                player_choices pc
            LEFT JOIN 
                members m ON pc.user_id = m.user_id
            GROUP BY 
                pc.user_id, m.user_name
            ORDER BY 
                total_runs DESC
            LIMIT 50
        """)
        user_data = cursor.fetchall()
        
        # For each user, get more details
        for user in user_data:
            user_id = user['user_id']
            
            # Get total points and completion rate
            cursor.execute("""
                SELECT 
                    SUM(points) as total_points,
                    COUNT(DISTINCT run_id) as runs_with_points,
                    COUNT(DISTINCT CASE WHEN points >= 10 THEN run_id END) as completed_runs
                FROM 
                    user_points
                WHERE 
                    user_id = %s
            """, (user_id,))
            
            points_data = cursor.fetchone()
            
            # Get the user's most common choice
            cursor.execute("""
                SELECT 
                    choice,
                    node_id,
                    COUNT(*) as choice_count
                FROM 
                    player_choices
                WHERE 
                    user_id = %s
                GROUP BY 
                    choice, node_id
                ORDER BY 
                    choice_count DESC
                LIMIT 1
            """, (user_id,))
            
            common_choice_data = cursor.fetchone()
            common_choice_text = "N/A"
            
            if common_choice_data:
                # Get node title if available
                cursor.execute("""
                    SELECT title FROM story_nodes WHERE id = %s
                """, (common_choice_data['node_id'],))
                node = cursor.fetchone()
                
                node_title = node['title'] if node else common_choice_data['node_id']
                choice_text = common_choice_data['choice'].replace('_', ' ').capitalize()
                common_choice_text = f"{node_title}: {choice_text}"
            
            # Use the actual username if available, otherwise use user ID
            username = user['user_name'] if user.get('user_name') else f"User {user_id[-4:]}" if user_id else "Unknown"
            
            user_stats.append({
                'user_id': user_id,
                'username': username,
                'runs': user['total_runs'],
                'stories_played': user['stories_played'],
                'completed_runs': points_data['completed_runs'] if points_data else 0,
                'completion_rate': round((points_data['completed_runs'] / user['total_runs']) * 100, 1) if points_data and user['total_runs'] > 0 else 0,
                'last_played': user['last_played'],
                'common_choice': common_choice_text
            })
    
    return user_stats

def get_analytics_summary():
    """Get overall analytics summary"""
    conn = get_db()
    summary = {}
    
    with conn.cursor() as cursor:
        # Get total stories, nodes, runs and users using player_choices and user_points tables
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM stories) as total_stories,
                (SELECT COUNT(*) FROM story_nodes) as total_nodes,
                (SELECT COUNT(DISTINCT run_id) FROM player_choices) as total_runs,
                (SELECT COUNT(DISTINCT run_id) FROM user_points WHERE points >= 10) as completed_runs,
                (SELECT COUNT(DISTINCT user_id) FROM player_choices) as active_users
        """)
        summary = cursor.fetchone()
        
        # Calculate completion rate
        if summary and summary['total_runs'] > 0:
            summary['completion_rate'] = round((summary['completed_runs'] / summary['total_runs']) * 100, 1)
        else:
            summary['completion_rate'] = 0
    
    return summary


def get_custom_actions(page=1, per_page=25, run_id=None):
    """Get custom actions with pagination and filtering"""
    conn = get_db()
    actions = []
    total_count = 0
    offset = (page - 1) * per_page
    
    with conn.cursor() as cursor:
        # Build the query with optional run_id filter
        count_query = "SELECT COUNT(*) as count FROM custom_actions"
        query = """
            SELECT 
                ca.id,
                ca.guild_id,
                ca.node_id,
                ca.run_id,
                ca.user_id,
                ca.text,
                ca.submitted_at,
                m.user_name,
                sn.title as node_title
            FROM 
                custom_actions ca
            LEFT JOIN 
                members m ON ca.user_id = m.user_id
            LEFT JOIN
                story_nodes sn ON ca.node_id = sn.id
        """
        
        params = []
        if run_id:
            count_query += " WHERE run_id = %s"
            query += " WHERE ca.run_id = %s"
            params.append(run_id)
        
        # Get total count for pagination
        cursor.execute(count_query, tuple(params))
        result = cursor.fetchone()
        total_count = result['count'] if result else 0
        
        # Get paginated results
        query += " ORDER BY ca.submitted_at DESC LIMIT %s OFFSET %s"
        params.append(per_page)
        params.append(offset)
        
        cursor.execute(query, tuple(params))
        actions = cursor.fetchall()
    
    return {
        'actions': actions,
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'pages': (total_count + per_page - 1) // per_page
    }
