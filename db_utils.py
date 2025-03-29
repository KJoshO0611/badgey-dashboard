import mysql.connector
from flask import current_app, g

def get_db_connection():
    if 'db' not in g:
        g.db = mysql.connector.connect(
            host=current_app.config['DATABASE']['host'],
            port=current_app.config['DATABASE']['port'],
            user=current_app.config['DATABASE']['user'],
            password=current_app.config['DATABASE']['password'],
            database=current_app.config['DATABASE']['database']
        )
    return g.db 