from flask import Flask, g, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import pool
import boto3
from werkzeug.utils import secure_filename
import os


app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

s3 = boto3.client('s3')

@app.route('/status')
def status():
    return "Gunicorn is running!", 200


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        tmp_filepath = os.path.join('/tmp', filename)
        file.save(tmp_filepath)
        try:
            response = s3.upload_file(tmp_filepath, 'alex-chen', filename)
            url = f"https://alex-chen.s3.us-west-1.amazonaws.com/{filename}"
            # Cleanup temp file
            os.remove(tmp_filepath)
            return jsonify({"url": url})
        except Exception as e:
            # You can log the exception for debugging
            return jsonify({"error": "File upload failed"}), 500


# Database connection configuration

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
    # Check if db instance is set, if not get a new connection
    if 'db' not in g:
        g.db = db_pool.getconn()

    return g.db


@app.teardown_appcontext
def close_db(error):
    # If this request used the database, close the used connection
    db = g.pop('db', None)

    if db is not None:
        db_pool.putconn(db)


# Sample caregiver data (you can replace this with your actual database integration)
caregivers = [
    {"id": 1, "name": "John Doe", "description": "Experienced caregiver"},
    {"id": 2, "name": "Jane Smith", "description": "Compassionate nanny"},
    # Add more caregivers as needed
]


@app.route("/api/caregivers", methods=["GET"])
def get_caregivers():
    # Connect to the PostgreSQL database
    conn = get_db()
    cursor = conn.cursor()

    # Fetch caregivers from the database
    cursor.execute("SELECT * FROM caregivers")
    rows = cursor.fetchall()

    # Close the connection
    cursor.close()

    # Format the data for JSON
    caregivers = [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            # add the rest of your fields here, make sure to match the order they appear in your database
            "years_of_experience": row[3],
            "age": row[4],
            "education": row[5],
            "gender": row[6],
            "phone": row[7],
            "imageUrl": row[8]
        }
        for row in rows
    ]

    return jsonify(caregivers)


@app.route("/api/caregivers/<int:caregiver_id>", methods=["GET"])
def get_caregiver_detail(caregiver_id):
    # Connect to the PostgreSQL database
    conn = get_db()
    cursor = conn.cursor()

    # Fetch the specific caregiver from the database using the id
    cursor.execute("SELECT * FROM caregivers WHERE id = %s", (caregiver_id,))
    row = cursor.fetchone()

    # Close the connection
    cursor.close()

    # Check if a caregiver with the given id exists
    if not row:
        return jsonify({"error": "Caregiver not found"}), 404

    # Format the data for JSON
    caregiver = {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "years_of_experience": row[3],
        "age": row[4],
        "education": row[5],
        "gender": row[6],
        "phone": row[7],
        "imageUrl": row[8]
    }

    return jsonify(caregiver)


@app.route("/api/caregivers", methods=["POST"])
def add_caregiver():
    data = request.get_json()

    # Connect to the PostgreSQL database
    conn = get_db()
    cursor = conn.cursor()

    # Define the columns and values for the INSERT query
    columns = ["name", "phone", "description", "imageUrl"]

    values = [data[field] for field in columns]

    # Optional fields: yearsOfExperience, age, education, gender
    # Add them to the INSERT query only if they are present in the data
    optional_fields = ["years_of_experience", "age", "education", "gender"]
    for field in optional_fields:
        if field in data:
            columns.append(field)
            values.append(data[field])
        else:
            # If the optional field is missing, set a default value or NULL
            # For example, set the yearsOfExperience to NULL
            # You can customize the default values as needed
            columns.append(field)
            values.append(None)

    # Construct the INSERT query with the appropriate number of placeholders
    insert_query = f"INSERT INTO caregivers ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) RETURNING id"

    # Execute the INSERT query with the values
    cursor.execute(insert_query, values)
    new_caregiver_id = cursor.fetchone()[0]

    # Commit the changes and close the connection
    conn.commit()
    cursor.close()

    # Return the newly created caregiver data with the assigned ID
    new_caregiver = {
        "id": new_caregiver_id,
        "name": data["name"],
        "phone": data["phone"],
        "description": data["description"],
        "age": data["age"],
        "education": data["education"],
        "gender": data["gender"],
        "years_of_experience": data["years_of_experience"],
        "imageUrl": data["imageUrl"],
    }
    return jsonify(new_caregiver), 201


if __name__ == "__main__":
    app.run(debug=True)
