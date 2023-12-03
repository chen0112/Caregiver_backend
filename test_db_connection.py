import psycopg2

# Database configuration
db_config = {
    "dbname": "caregiverdb",
    "user": "alex_chen",
    "password": "Cyf19960112",
    "host": "18.163.28.129",  # Use your EC2 instance's IP
    "port": "5432",
}

try:
    # Connect to your postgres DB
    conn = psycopg2.connect(**db_config)

    # Open a cursor to perform database operations
    cur = conn.cursor()

    # Execute a query
    cur.execute("SELECT version();")

    # Retrieve query results
    version = cur.fetchone()
    print("Connected to PostgreSQL version:", version)

    # Close cursor and connection
    cur.close()
    conn.close()

except psycopg2.OperationalError as e:
    print("Unable to connect to the database:", e)
