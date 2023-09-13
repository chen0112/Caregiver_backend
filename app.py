from psycopg2.extras import DictCursor  # Assuming you are using psycopg2
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

            # Check if the user has posted forms before in animalcaregiverform table
            cursor.execute(
                "SELECT COUNT(*) FROM animalcaregiverform WHERE phone = %s", (phone,))
            has_posted_ads_animalcaregiverform = cursor.fetchone()[0] > 0

            has_posted_ads = has_posted_ads_caregivers or has_posted_ads_careneeders or has_posted_ads_animalcaregiverform

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
        cursor.execute(
            "SELECT * FROM caregivers WHERE phone = %s ORDER BY id DESC", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Caregivers not found"}), 404

        caregivers = [
            {
                "id": row["id"],
                "name": row["name"],
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
        mandatory_columns = ["name", "phone", "location"]
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

         # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(mandatory_columns)
        values_placeholder = ', '.join(['%s'] * len(mandatory_columns))
        insert_query = f"INSERT INTO careneeder ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

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
        cursor.execute(
            "SELECT * FROM careneeder WHERE phone = %s ORDER BY id DESC", (phone,))
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


@app.route("/api/mycaregiver/<int:id>/ad", methods=["PUT"])
def update_caregiver_ad(id):
    app.logger.debug(f"Entering update_caregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE caregiverads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE caregiver_id = {id}"

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


@app.route("/api/careneeder_schedule", methods=["POST"])
def add_schedule():
    try:
        data = request.get_json()

        # Log the received data for debugging
        app.logger.debug("Received data: %s", data)

        # Validate that careneeder_id is provided
        if "careneeder_id" not in data:
            return jsonify({"error": "careneeder_id is required"}), 400

        # Define the columns for the INSERT query
        columns = ["scheduletype", "totalhours", "frequency",
                   "startdate", "selectedtimeslots", "durationdays", "careneeder_id"]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in columns:
            if column in data:
                values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO careneederschedule ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_schedule_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the Schedule interface
        new_schedule = {
            "id": new_schedule_id,
        }

        # Include columns in the return object if they exist
        for column in columns:
            if column in data:
                new_schedule[column] = data[column]

        return jsonify(new_schedule), 201

    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.error(f"Error adding schedule: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add schedule"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/mycareneeder/<int:id>/ad", methods=["PUT"])
def update_careneeder_ad(id):
    app.logger.debug(f"Entering update_careneeder for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE careneederads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE careneeder_id = {id}"

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



@app.route("/api/careneeder_ads", methods=["POST"])
def add_careneeder_ad():
    try:
        data = request.get_json()

        # Define the columns for the INSERT query
        columns = ["title", "description",  "careneeder_id"]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in columns:
            if column in data:
                values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO careneederads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_ad_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the ad interface
        new_ad = {
            "id": new_ad_id,
        }

        # Include columns in the return object if they exist
        for column in columns:
            if column in data:
                new_ad[column] = data[column]

        return jsonify(new_ad), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        app.logger.error(
            f"Error adding careneeder ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add careneeder ad"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/all_careneederschedule', methods=['GET'])
def get_all_careneederschedule():
    app.logger.info("Entering GET /api/all_careneederschedule request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneederschedule data from the database
        cursor.execute("SELECT * FROM careneederschedule ORDER BY id DESC")
        rows = cursor.fetchall()
        app.logger.debug(
            f"Fetched {len(rows)} careneederschedule records from the database")

        # Close the connection
        cursor.close()

        if not rows:
            app.logger.warning(
                "No careneederschedule records found in the database")
            return jsonify({"error": "No careneederschedule data available"}), 404

        # Format the data for JSON

        careneederschedule = [dict(row) for row in rows]

        app.logger.debug("Successfully processed all careneederschedule data")

        response = make_response(jsonify(careneederschedule))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        app.logger.error(
            "Error fetching all careneederschedule", exc_info=True)
        return jsonify({"error": "Failed to fetch all careneederschedule"}), 500


@app.route("/api/all_careneederads", methods=["GET"])
def get_careneeder_ads():
    conn = None
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        # Use DictCursor to fetch rows as dictionaries
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Execute the SELECT query to fetch all records from the table
        select_query = "SELECT * FROM careneederads ORDER BY id DESC"
        cursor.execute(select_query)

        # Fetch all rows and close the cursor
        rows = cursor.fetchall()
        cursor.close()

        app.logger.debug(
            f"Fetched {len(rows)} careneederads records from the database")

        # Check the data type of the first row for debugging
        if rows:
            app.logger.debug(f"First row data type: {type(rows[0])}")

        if not rows:
            app.logger.warning(
                "No careneederads records found in the database")
            return jsonify({"error": "No careneederads data available"}), 404

        careneederads = [dict(row) for row in rows]

        app.logger.debug("Successfully processed all careneederads data")

        response = make_response(jsonify(careneederads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        app.logger.error(
            f"Error fetching careneeder ads: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeder ads"}), 500

    finally:
        if conn:
            conn.close()


@app.route("/api/caregiver_ads", methods=["POST"])
def add_caregiver_ad():
    try:
        data = request.get_json()

        # Define the columns for the INSERT query
        columns = ["title", "description", "caregiver_id"]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in columns:
            if column in data:
                values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO caregiverads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_ad_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the ad interface
        new_ad = {
            "id": new_ad_id,
        }

        # Include columns in the return object if they exist
        for column in columns:
            if column in data:
                new_ad[column] = data[column]

        return jsonify(new_ad), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        app.logger.error(f"Error adding caregiver ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver ad"}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/all_caregiverads", methods=["GET"])
def get_caregiver_ads():
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        # Use DictCursor to fetch rows as dictionaries
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Execute the SELECT query to fetch all records from the caregiverads table
        select_query = "SELECT * FROM caregiverads ORDER BY id DESC"
        cursor.execute(select_query)

        # Fetch all rows and close the cursor
        rows = cursor.fetchall()
        cursor.close()

        app.logger.debug(
            f"Fetched {len(rows)} caregiverads records from the database")

        # Check the data type of the first row for debugging
        if rows:
            app.logger.debug(f"First row data type: {type(rows[0])}")

        if not rows:
            app.logger.warning(
                "No caregiverads records found in the database")
            return jsonify({"error": "No caregiverads data available"}), 404

        caregiverads = [dict(row) for row in rows]

        app.logger.debug("Successfully processed all caregiverads data")

        response = make_response(jsonify(caregiverads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        app.logger.error(
            f"Error fetching caregiver ads: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver ads"}), 500

    finally:
        if conn:
            conn.close()


@app.route("/api/animalcaregiver_details", methods=["POST"])
def add_animalcaregiver_detail():
    conn = None
    try:
        data = request.get_json()
        print("Received data:", data)

        # Define the columns for the INSERT query
        columns = ["\"animalcaregiverid\"", "\"selectedservices\"",
                   "\"selectedanimals\"", "\"hourlycharge\""]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in ["animalcaregiverid", "selectedservices", "selectedanimals", "hourlycharge"]:
            if column in data:
                if column == 'selectedservices' or column == 'selectedanimals':
                    # Convert list of strings to PostgreSQL array format
                    values.append('{'+','.join(map(str, data[column]))+'}')
                else:
                    values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f'INSERT INTO animalcaregiver ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id'

        print("Inserting values:", values)  # Debugging line
        print(f"Executing SQL: {insert_query % tuple(values)}")

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_detail_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the interface
        new_detail = {
            "id": new_detail_id,
        }

        # Include columns in the return object if they exist
        for column in ["animalcaregiverid", "selectedservices", "selectedanimals", "hourlycharge"]:
            if column in data:
                new_detail[column] = data[column]

        return jsonify(new_detail), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        app.logger.error(
            f"Error adding animalcaregiver detail: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcaregiver detail"}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/all_animalcaregivers", methods=["POST"])
def add_animalcaregiver():
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
        insert_query = f"INSERT INTO animalcaregiverform ({', '.join(mandatory_columns)}) VALUES ({', '.join(['%s'] * len(mandatory_columns))}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_animalcaregiver_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Return the newly created caregiver data with the assigned ID
        # imageUrl is possibly from const [imageUrl, setImageUrl] = useState<string | null>(null) in CaregiverForm.tsx
        new_animalcaregiverform = {
            "id": new_animalcaregiver_id,
            "name": data["name"],
            "phone": data["phone"],
            "age": data["age"],
            "education": data["education"],
            "gender": data["gender"],
            "years_of_experience": data["years_of_experience"],
            "imageurl": data["imageurl"],
            "location": data["location"]
        }
        return jsonify(new_animalcaregiverform), 201

    except Exception as e:
        logger.error(
            f"Error adding animalcaregiverform: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcaregiverform"}), 500


@app.route("/api/animalcaregiver_ads", methods=["POST"])
def add_animal_caregiver_ad():
    conn = None
    try:
        data = request.get_json()

        # Validate if "animalcaregiverid", "title", and "description" are present in data
        if not all(key in data for key in ["animalcaregiverid", "title", "description"]):
            return jsonify({"error": "Required fields are missing"}), 400

        # Define the columns for the INSERT query
        columns = ["title", "description", "animalcaregiverid"]

        # Initialize values list
        values = [data["title"], data["description"],
                  data["animalcaregiverid"]]

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO animalcaregiverads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_animalcaregiver_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the ad interface
        new_ad = {
            "id": new_animalcaregiver_id,
            "title": data["title"],
            "description": data["description"],
            "animalcaregiverid": data["animalcaregiverid"]
        }

        return jsonify(new_ad), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        logger.error(
            f"Error adding animal caregiver ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animal caregiver ad"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/all_animalcaregivers', methods=['GET'])
def get_all_animal_caregivers():
    app.logger.info(
        "---------------Entering GET /api/all_animal_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcaregiverform ORDER BY id DESC")
        rows = cursor.fetchall()
        app.logger.debug(
            f"Fetched {len(rows)} animal caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            app.logger.warning("No animal caregivers found in the database")
            return jsonify({"error": "Problem of fetching animal caregivers"}), 404

        # Directly convert the rows into JSON
        animal_caregivers = [dict(row) for row in rows]

        # Format the data for JSON
        animal_caregivers = [
            {
                "id": row["id"],
                "name": row["name"],
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

        app.logger.debug("Successfully processed all animal caregivers data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        app.logger.error("Error fetching all animal caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal caregivers"}), 500


@app.route('/api/all_animal_caregivers_details', methods=['GET'])
def get_all_animal_caregivers_details():
    app.logger.info(
        "---------------Entering GET /api/all_animal_caregivers details request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcaregiver ORDER BY id DESC")
        rows = cursor.fetchall()
        app.logger.debug(
            f"Fetched {len(rows)} animal caregivers details from the database")

        # Close the connection
        cursor.close()

        if not rows:
            app.logger.warning(
                "No animal caregivers details found in the database")
            return jsonify({"error": "Problem fetching animal caregivers details"}), 404

        # Directly convert the rows into JSON
        animal_caregivers = [
            {
                "id": row["id"],
                "animalcaregiverid": row["animalcaregiverid"],
                "selectedservices": row["selectedservices"],
                "selectedanimals": row["selectedanimals"],
                "hourlycharge": row["hourlycharge"]
            }
            for row in rows
        ]

        app.logger.debug(
            "Successfully processed all animal caregivers details data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        app.logger.error(
            "Error fetching all animal caregivers details", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal caregivers details"}), 500


@app.route('/api/all_animal_caregiver_ads', methods=['GET'])
def get_all_animal_caregiver_ads():
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Using the correct table name
        cursor.execute("SELECT * FROM animalcaregiverads ORDER BY id DESC")
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return jsonify({"error": "No animal caregiver ads found"}), 404

        animal_caregiver_ads = [
            {
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "animalcaregiverid": row["animalcaregiverid"]
            }
            for row in rows
        ]

        response = make_response(jsonify(animal_caregiver_ads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        return jsonify({"error": "Failed to fetch animal caregiver ads"}), 500


@app.route("/api/all_animalcaregiverform/<int:animalcaregiverform_id>", methods=["GET"])
def get_animalcaregiverform_detail(animalcaregiverform_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the specific record from the animalcaregiverform table using the id
        cursor.execute(
            "SELECT * FROM animalcaregiverform WHERE id = %s", (animalcaregiverform_id,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        # Check if a record with the given id exists
        if not row:
            return jsonify({"error": "Animal Caregiver Form not found"}), 404

        # Format the data for JSON (update these keys as needed)
        animalcaregiverform = {
            "id": row["id"],
            "name": row["name"],
            "years_of_experience": row["years_of_experience"],
            "age": row["age"],
            "education": row["education"],
            "gender": row["gender"],
            "phone": row["phone"],
            "imageurl": row["imageurl"],
            "location": row["location"]
        }

        return jsonify(animalcaregiverform)
    except Exception as e:
        logger.error(
            f"Error fetching animal caregiver form detail for id {animalcaregiverform_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal caregiver form detail"}), 500


@app.route("/api/myanimalcaregiverform/<phone>", methods=["GET"])
def get_myanimalcaregiverform(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the records related to the phone number from the animalcaregiverform table
        cursor.execute(
            "SELECT * FROM animalcaregiverform WHERE phone = %s ORDER BY id DESC", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Animal Caregiver Forms not found"}), 404

        animalcaregiverforms = [
            {
                "id": row["id"],
                "name": row["name"],
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

        return jsonify(animalcaregiverforms)
    except Exception as e:
        app.logger.error(
            f"Error fetching animal caregiver forms for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal caregiver forms"}), 500

@app.route("/api/myanimalcaregiver/<int:id>/ad", methods=["PUT"])
def update_animalcaregiver_ad(id):
    app.logger.debug(f"Entering update_animalcaregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE animalcaregiverads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE animalcaregiverid = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        app.logger.info(f"Received data: {data}")
        app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        app.logger.error(f"Error updating animal caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update animal caregiver"}), 500
   


if __name__ == "__main__":
    app.run(debug=True)
