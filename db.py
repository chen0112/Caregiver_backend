# db.py
from flask import g
import psycopg2.pool
import os

# Database configuration
db_config = {
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT"),
}

# Setting up a connection pool
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, **db_config)

def get_db():
    if 'db' not in g:
        g.db = db_pool.getconn()
    return g.db

def close_db(error):
    # If this request used the database, close the used connection
    db = g.pop('db', None)

    if db is not None:
        db_pool.putconn(db)