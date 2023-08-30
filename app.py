from flask import Flask, g, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import pool
import boto3
from werkzeug.utils import secure_filename
import os
from psycopg2.extras import DictCursor
import logging
from flask import make_response
import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
import bcrypt
import json


logging.basicConfig(filename='/home/ubuntu/Caregiver_backend/app.log', level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
logger = logging.getLogger(__name__)


app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# Adding a file handler to write Flask's log messages to the same file
file_handler = logging.FileHandler('/home/ubuntu/Caregiver_backend/app.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'))
app.logger.addHandler(file_handler)

CORS(app, resources={r"/*": {"origins": "*"}})

s3 = boto3.client('s3')


@app.route('/status')
def status():
    app.logger.info('Status endpoint was called')
    return "Gunicorn is running!", 200


@app.route("/test_put", methods=["PUT"])
def test_put():
    return jsonify({"success": "PUT request successful"}), 200


@app.route("/api/register", methods=["POST"])
def register():
    try:
        # Get the JSON data from the request
        data = request.get_json()

        # Extract phone and passcode
        phone = data["phone"]
        passcode = data["passcode"]  # this is already hashed from the frontend

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Check if the phone number already exists in the accounts table
        cursor.execute("SELECT * FROM accounts WHERE phone = %s", (phone,))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({"error": "手机号已被注册"}), 400

        # Insert the new account into the database
        createtime = datetime.datetime.now()
        cursor.execute("INSERT INTO accounts (phone, passcode, createtime) VALUES (%s, %s, %s) RETURNING id",
                       (phone, passcode, createtime))
        new_user_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Return success response
        return jsonify({"success": True, "message": "创建账号成功!", "id": new_user_id}), 201

    except Exception as e:
        app.logger.info(f"Error registering user: {str(e)}", exc_info=True)
        return jsonify({"error": "创建失败！"}), 500


@app.route('/api/signin', methods=['POST'])
def sign_in():
    phone = request.json['phone']
    passcode = request.json['passcode']

    conn = get_db()  # Connection details
    cursor = conn.cursor()

    # Fetch the hashed passcode from the database
    cursor.execute("SELECT passcode FROM accounts WHERE phone = %s", (phone,))
    result = cursor.fetchone()

    if result:
        hashed_passcode = result[0]
        # Verify the hashed passcode
        if bcrypt.checkpw(passcode.encode('utf-8'), hashed_passcode.encode('utf-8')):
            # Check if the user has posted ads before
            cursor.execute(
                "SELECT COUNT(*) FROM caregivers WHERE phone = %s", (phone,))
            has_posted_ads_caregivers = cursor.fetchone()[0] > 0

            # Check if the user has posted ads in careneeders table
            cursor.execute(
                "SELECT COUNT(*) FROM careneeder WHERE phone = %s", (phone,))
            has_posted_ads_careneeders = cursor.fetchone()[0] > 0

            has_posted_ads = has_posted_ads_caregivers or has_posted_ads_careneeders

            return jsonify(success=True, hasPostedAds=has_posted_ads), 200
        else:
            return jsonify(success=False, message='密码不正确'), 401
    else:
        return jsonify(success=False, message='电话号码不正确'), 404


@app.route("/api/mycaregiver/<phone>", methods=["GET"])
def get_mycaregivers(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the caregivers related to the phone number
        cursor.execute("SELECT * FROM caregivers WHERE phone = %s", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Caregivers not found"}), 404

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
                "imageurl": row["imageurl"],
                "location": row["location"]
            }
            for row in rows
        ]

        return jsonify(caregivers)
    except Exception as e:
        app.logger.error(
            f"Error fetching caregivers for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregivers"}), 500


@app.route("/api/mycaregiver/<int:id>", methods=["PUT"])
def update_caregiver(id):
    app.logger.debug(f"Entering update_caregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        # Added location to the list
        columns = ["name", "description", "location"]
        # Using .get() to avoid KeyError
        values = []

        for field in columns:
            value = data.get(field, None)
            if field == 'location' and isinstance(value, list):
                # Serialize dict to JSON string
                values.append(json.dumps(value))
            else:
                values.append(value)

        app.logger.debug(f"Serialized location: {json.dumps(value)}")
        app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE caregivers SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + f" WHERE id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        app.logger.info(f"Received data: {data}")
        app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        app.logger.error(f"Error updating caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update caregiver"}), 500


@app.route('/api/all_caregivers', methods=['GET'])
def get_all_caregivers():
    app.logger.info("---------------Entering GET /api/all_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch caregivers from the database
        cursor.execute("SELECT * FROM caregivers ORDER BY id DESC")
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
                "imageurl": row["imageurl"],
                "location": row["location"]
            }
            for row in rows
        ]

        app.logger.debug("Successfully processed all caregivers data")

        response = make_response(jsonify(caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        app.logger.error("Error fetching all caregivers", exc_info=True)
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


@app.route("/api/all_caregivers/<int:caregiver_id>", methods=["GET"])
def get_caregiver_detail(caregiver_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the specific caregiver from the database using the id
        cursor.execute("SELECT * FROM caregivers WHERE id = %s",
                       (caregiver_id,))
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
            "imageurl": row["imageurl"],
            "location": row["location"]
        }

        return jsonify(caregiver)
    except Exception as e:
        logger.error(
            f"Error fetching caregiver detail for id {caregiver_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver detail"}), 500


@app.route("/api/all_caregivers", methods=["POST"])
def add_caregiver():
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the mandatory columns and values for the INSERT query
        mandatory_columns = ["name", "phone", "imageurl", "location"]
        values = [data[field] if field != 'location' else json.dumps(
            data[field]) for field in mandatory_columns]

        # Optional fields: yearsOfExperience, age, education, gender
        # Add them to the INSERT query only if they are present in the data
        optional_fields = ["years_of_experience", "age", "education", "gender"]
        for field in optional_fields:
            if field in data:
                mandatory_columns.append(field)
                values.append(data[field])
            else:
                # If the optional field is missing, set a default value or NULL
                # For example, set the yearsOfExperience to NULL
                # You can customize the default values as needed
                mandatory_columns.append(field)
                values.append(None)

        # Construct the INSERT query with the appropriate number of placeholders
        insert_query = f"INSERT INTO caregivers ({', '.join(mandatory_columns)}) VALUES ({', '.join(['%s'] * len(mandatory_columns))}) RETURNING id"

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
            "location": data["location"]
        }
        return jsonify(new_caregiver), 201

    except Exception as e:
        logger.error(f"Error adding caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver"}), 500


@app.route("/api/all_careneeders", methods=["POST"])
def add_careneeder():
    try:
        data = request.get_json()

        # Validate mandatory fields
        for field in ["name", "phone"]:
            if field not in data:
                return jsonify({"error": f"{field} is required"}), 400

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the mandatory columns and values for the INSERT query
        mandatory_columns = ["name", "phone", "imageurl", "location"]
        values = [data[field] if field != 'location' else json.dumps(
            data[field]) for field in mandatory_columns]

        # Define optional fields and include them in columns and values if they are present
        optional_fields = [
            "live_in_care", "live_out_care", "domestic_work", "meal_preparation",
            "companionship", "washing_dressing", "nursing_health_care",
            "mobility_support", "transportation", "errands_shopping"
        ]

        for field in optional_fields:
            if field in data:
                mandatory_columns.append(field)
                values.append(data[field])
            else:
                mandatory_columns.append(field)
                values.append(None)

        # Construct the INSERT query
        insert_query = f"INSERT INTO careneeder ({', '.join(mandatory_columns)}) VALUES ({', '.join(['%s'] * len(mandatory_columns))}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_careneeder_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the Careneeder interface
        new_careneeder = {
            "id": new_careneeder_id,
            "name": data["name"],
            "phone": data["phone"],
            "imageurl": data["imageurl"],
            "location": data["location"]
        }

        # Include optional fields in the return object if they exist
        for field in optional_fields:
            new_careneeder[field] = data.get(field, None)

        return jsonify(new_careneeder), 201

    except Exception as e:  # Could also catch specific exceptions like psycopg2.DatabaseError
        if conn:
            conn.rollback()  # Rolling back in case of an error
        app.logger.error(f"Error adding careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add careneeder"}), 500
    finally:
        if conn:
            conn.close()  # Ensure that the connection is closed or returned to the pool


@app.route('/api/all_careneeders', methods=['GET'])
def get_all_careneeders():
    app.logger.info("---------------Entering GET /api/all_careneeders request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneeders from the database
        cursor.execute("SELECT * FROM careneeder ORDER BY id DESC")
        rows = cursor.fetchall()
        app.logger.debug(f"Fetched {len(rows)} careneeders from the database")

        # Close the connection
        cursor.close()

        if not rows:
            app.logger.warning("No careneeders found in the database")
            return jsonify({"error": "Problem of fetching careneeders"}), 404

        # Directly convert the rows into JSON
        careneeders = [dict(row) for row in rows]

        # Format the data for JSON
        careneeders = [
            {
                "id": row["id"],
                "name": row["name"],
                "phone": row["phone"],
                "imageurl": row["imageurl"],
                "live_in_care": row["live_in_care"],
                "live_out_care": row["live_out_care"],
                "domestic_work": row["domestic_work"],
                "meal_preparation": row["meal_preparation"],
                "companionship": row["companionship"],
                "washing_dressing": row["washing_dressing"],
                "nursing_health_care": row["nursing_health_care"],
                "mobility_support": row["mobility_support"],
                "transportation": row["transportation"],
                "errands_shopping": row["errands_shopping"],
                "location": row["location"]
            }
            for row in rows
        ]

        app.logger.debug("Successfully processed all careneeders data")

        response = make_response(jsonify(careneeders))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        app.logger.error("Error fetching all careneeders", exc_info=True)
        return jsonify({"error": "Failed to fetch all careneeders"}), 500


@app.route("/api/all_careneeders/<int:careneeder_id>", methods=["GET"])
def get_careneeder_detail(careneeder_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the specific careneeder from the database using the id
        cursor.execute("SELECT * FROM careneeder WHERE id = %s",
                       (careneeder_id,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        # Check if a careneeder with the given id exists
        if not row:
            return jsonify({"error": "Careneeder not found"}), 404

        # Format the data for JSON
        careneeder = {
            "id": row["id"],
            "name": row["name"],
            "phone": row["phone"],
            "imageurl": row["imageurl"],
            "live_in_care": row["live_in_care"],
            "live_out_care": row["live_out_care"],
            "domestic_work": row["domestic_work"],
            "meal_preparation": row["meal_preparation"],
            "companionship": row["companionship"],
            "washing_dressing": row["washing_dressing"],
            "nursing_health_care": row["nursing_health_care"],
            "mobility_support": row["mobility_support"],
            "transportation": row["transportation"],
            "errands_shopping": row["errands_shopping"],
            "location": row["location"]
        }

        return jsonify(careneeder)
    except Exception as e:
        logger.error(
            f"Error fetching careneeder detail for id {careneeder_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeder detail"}), 500


@app.route("/api/mycareneeder/<phone>", methods=["GET"])
def get_mycareneeders(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the careneeders related to the phone number
        cursor.execute("SELECT * FROM careneeder WHERE phone = %s", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Careneeders not found"}), 404

        careneeders = [
            {
                "id": row["id"],
                "name": row["name"],
                "phone": row["phone"],
                "imageurl": row["imageurl"],
                "live_in_care": row["live_in_care"],
                "live_out_care": row["live_out_care"],
                "domestic_work": row["domestic_work"],
                "meal_preparation": row["meal_preparation"],
                "companionship": row["companionship"],
                "washing_dressing": row["washing_dressing"],
                "nursing_health_care": row["nursing_health_care"],
                "mobility_support": row["mobility_support"],
                "transportation": row["transportation"],
                "errands_shopping": row["errands_shopping"],
                "location": row["location"]
            }
            for row in rows
        ]

        return jsonify(careneeders)
    except Exception as e:
        app.logger.error(
            f"Error fetching careneeders for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeders"}), 500

@app.route("/api/mycareneeder/<int:id>", methods=["PUT"])
def update_careneeder(id):
    app.logger.debug(f"Entering update_careneeder for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        # Added location to the list
        columns = ["name", "location"]
        # Using .get() to avoid KeyError
        values = []

        for field in columns:
            value = data.get(field, None)
            if field == 'location' and isinstance(value, list):
                # Serialize dict to JSON string
                values.append(json.dumps(value))
            else:
                values.append(value)

        app.logger.debug(f"Serialized location: {json.dumps(value)}")
        app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE careneeder SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + f" WHERE id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        app.logger.info(f"Received data: {data}")
        app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        app.logger.error(f"Error updating careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update careneeder"}), 500


if __name__ == "__main__":
    app.run(debug=True)
