import datetime
from flask import Flask, g, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import pool
import boto3
from werkzeug.utils import secure_filename
import os
from os import environ
from psycopg2.extras import DictCursor
import logging
from flask import make_response
from twilio.rest import Client
import random


logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
logger = logging.getLogger(__name__)
# home/ubuntu/Caregiver_backend/


app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# Adding a file handler to write Flask's log messages to the same file
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'))
app.logger.addHandler(file_handler)

CORS(app, resources={r"/*": {"origins": "*"}})

s3 = boto3.client('s3')

def generate_otp():
    return random.randint(100000, 999999)


TWILIO_ACCOUNT_SID = environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = environ.get('TWILIO_PHONE_NUMBER')

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    try:
        phone = request.json.get('phone')
        otp = generate_otp()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Insert or update the OTP and timestamp for the corresponding phone number in the new table
        cursor.execute("INSERT INTO otp_verification (phone, otp) VALUES (%s, %s) ON CONFLICT (phone) DO UPDATE SET otp = %s, otp_timestamp = CURRENT_TIMESTAMP", (phone, otp, otp))

        # Commit the changes
        conn.commit()

        # Close the connection
        cursor.close()

        message = twilio_client.messages.create(
            body=f"Your verification code is {otp}",
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )

        return jsonify({"success": "OTP sent successfully"}), 200
    except Exception as e:
        logger.error(f"Error sending OTP: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to send OTP"}), 500


@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    try:
        phone = request.json.get('phone')
        received_otp = request.json.get('otp')

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch OTP and timestamp from the new otp_verification table for the given phone number
        cursor.execute("SELECT otp, otp_timestamp FROM otp_verification WHERE phone = %s", (phone,))
        result = cursor.fetchone()


        if not result:
            app.logger.warning(f"No OTP found for phone number {phone}")
            return jsonify({"error": "Invalid phone number or OTP"}), 404

        stored_otp, otp_timestamp = result['otp'], result['otp_timestamp']

        # Close the connection
        cursor.close()

        # Verify if the OTP matches and is within a valid time frame (e.g., 5 minutes)
        if stored_otp == received_otp and (datetime.datetime.now() - otp_timestamp).total_seconds() < 300:
            return jsonify({"success": "OTP verified successfully"}), 200
        else:
            return jsonify({"error": "Invalid or expired OTP"}), 400

    except Exception as e:
        logger.error(f"Error verifying OTP: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to verify OTP"}), 500



@app.route('/status')
def status():
    app.logger.info('Status endpoint was called')
    return "Gunicorn is running!", 200

@app.route('/api/all_caregivers', methods=['GET'])
def get_all_caregivers():
    app.logger.info("---------------Entering GET /api/all_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch caregivers from the database
        cursor.execute("SELECT * FROM caregivers")
        rows = cursor.fetchall()
        app.logger.debug(f"Fetched {len(rows)} caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            app.logger.warning("No caregivers found in the database")
            return jsonify({"error": "Problem of fetching caregivers"}), 404

        # Directly convert the rows into JSON
        caregivers = [dict(row) for row in rows]

        # Format the data for JSON
        caregivers = [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "years_of_experience": row["years_of_experience"],
                "age": row["age"],
                "education": row["education"],
                "gender": row["gender"],
                "phone": row["phone"],
                "imageurl": row["imageurl"]
            }
            for row in rows
        ]

        app.logger.debug("Successfully processed all caregivers data")
        
        response = make_response(jsonify(caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        logger.error("Error fetching all caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch all caregivers"}), 500



@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        if file:
            filename = secure_filename(file.filename)
            tmp_filepath = os.path.join('/tmp', filename)
            file.save(tmp_filepath)
            response = s3.upload_file(tmp_filepath, 'alex-chen', filename)
            url = f"https://alex-chen.s3.us-west-1.amazonaws.com/{filename}"
            # Cleanup temp file
            os.remove(tmp_filepath)
            return jsonify({"url": url})
    except Exception as e:
        # You can log the exception for debugging
        logger.error("File upload failed", exc_info=True)
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
    app.logger.info("---------------Entering GET /api/caregivers request")
    app.logger.debug("Handling GET /api/caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch caregivers from the database
        cursor.execute("SELECT * FROM caregivers")
        rows = cursor.fetchall()
        app.logger.debug(f"Fetched {len(rows)} caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            app.logger.warning("No caregivers found in the database")
            return jsonify({"error": "Problem of fetching caregivers"}), 404

        # Format the data for JSON
        caregivers = [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "years_of_experience": row["years_of_experience"],
                "age": row["age"],
                "education": row["education"],
                "gender": row["gender"],
                "phone": row["phone"],
                "imageurl": row["imageurl"]
            }
            for row in rows
        ]

        logger.debug("Successfully processed caregivers data")

        response = make_response(jsonify(caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        logger.error("Error fetching caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch caregivers"}), 500



@app.route("/api/all_caregivers/<int:caregiver_id>", methods=["GET"])
def get_caregiver_detail(caregiver_id):
    try: 
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

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
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "years_of_experience": row["years_of_experience"],
            "age": row["age"],
            "education": row["education"],
            "gender": row["gender"],
            "phone": row["phone"],
            "imageurl": row["imageurl"]
        }

        return jsonify(caregiver)
    except Exception as e:
        logger.error(f"Error fetching caregiver detail for id {caregiver_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver detail"}), 500




@app.route("/api/all_caregivers", methods=["POST"])
def add_caregiver():
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the INSERT query
        columns = ["name", "phone", "description", "imageurl"]

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
        # imageUrl is possibly from const [imageUrl, setImageUrl] = useState<string | null>(null) in CaregiverForm.tsx
        new_caregiver = {
            "id": new_caregiver_id,
            "name": data["name"],
            "phone": data["phone"],
            "description": data["description"],
            "age": data["age"],
            "education": data["education"],
            "gender": data["gender"],
            "years_of_experience": data["years_of_experience"],
            "imageurl": data["imageurl"],
        }
        return jsonify(new_caregiver), 201
   
    except Exception as e:
        logger.error(f"Error adding caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver"}), 500



if __name__ == "__main__":
    app.run(debug=True)
