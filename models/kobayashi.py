from datetime import datetime
from models.db import get_db

# --- Story Model Functions ---
def get_all_stories():
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM stories ORDER BY id DESC')
        return cursor.fetchall()

def get_story(story_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM stories WHERE id = %s', (story_id,))
        return cursor.fetchone()

def create_story(title, intro, code, author):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO stories (title, intro, code, author, created_at) VALUES (%s, %s, %s, %s, %s)',
                       (title, intro, code, author, datetime.utcnow()))
    conn.commit()

def update_story(story_id, title, intro, code, author):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('UPDATE stories SET title = %s, intro = %s, code = %s, author = %s WHERE id = %s',
                       (title, intro, code, author, story_id))
    conn.commit()

def delete_story(story_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM stories WHERE id = %s', (story_id,))
    conn.commit()

# --- Node Model Functions ---
def get_nodes_for_story(story_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM story_nodes WHERE story_id = %s ORDER BY id', (story_id,))
        return cursor.fetchall()

def get_node(node_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM story_nodes WHERE id = %s', (node_id,))
        return cursor.fetchone()

import json

def create_node(story_id, node_data):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            '''INSERT INTO story_nodes
            (story_id, id, title, description, choices, conditions, is_terminal, ending_type, ending_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (
                story_id,
                node_data.get('id'),
                node_data.get('title'),
                node_data.get('description'),
                json.dumps(node_data.get('choices', {})),
                json.dumps(node_data.get('conditions', [])),
                int(node_data.get('is_terminal', 0)),
                node_data.get('ending_type'),
                node_data.get('ending_text'),
            )
        )
    conn.commit()

def update_node(node_id, node_data):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            '''UPDATE story_nodes SET
                title = %s,
                description = %s,
                choices = %s,
                conditions = %s,
                is_terminal = %s,
                ending_type = %s,
                ending_text = %s
            WHERE id = %s''',
            (
                node_data.get('title'),
                node_data.get('description'),
                json.dumps(node_data.get('choices', {})),
                json.dumps(node_data.get('conditions', [])),
                int(node_data.get('is_terminal', 0)),
                node_data.get('ending_type'),
                node_data.get('ending_text'),
                node_id
            )
        )
    conn.commit()

def delete_node(node_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM story_nodes WHERE id = %s', (node_id,))
    conn.commit()
