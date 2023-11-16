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
import bcrypt
import json
from datetime import datetime
import traceback

# AWS server will be /home/ubuntu/Caregiver_backend/app.log
# logging.basicConfig(filename='/home/alex_chen/Caregiver_backend/app.log', level=logging.INFO,
#                     format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

logging.basicConfig(filename='/home/ubuntu/Caregiver_backend/app.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

CORS(flask_app, resources={r"/*": {"origins": "*"}})

flask_app.logger.setLevel(logging.DEBUG)

# Adding a file handler to write Flask's log messages to the same file
# file_handler = logging.FileHandler('/home/alex_chen/Caregiver_backend/app.log')
file_handler = logging.FileHandler('/home/ubuntu/Caregiver_backend/app.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'))
flask_app.logger.addHandler(file_handler)

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


s3 = boto3.client('s3', region_name='ap-east-1')


@flask_app.route('/status')
def status():
    flask_app.logger.info('Status endpoint was called')
    return "Gunicorn is running good!", 200


@flask_app.route("/test_connection")
def test_connection():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM caregivers")
        results = cursor.fetchall()
        return jsonify({"status": "success", "message": "Connection to PostgreSQL database successful"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to connect to PostgreSQL database: {str(e)}"})


@flask_app.route("/test_put", methods=["PUT"])
def test_put():
    return jsonify({"success": "PUT request successful"}), 200


@flask_app.route("/api/register", methods=["POST"])
def register():
    try:
        # Get the JSON data from the request
        data = request.get_json()

        # Extract phone, passcode, name, and imageurl
        phone = data["phone"]
        passcode = data["passcode"]  # this is already hashed from the frontend
        name = data["name"]
        imageurl = data["imageurl"]

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Check if the phone number already exists in the accounts table
        cursor.execute("SELECT * FROM accounts WHERE phone = %s", (phone,))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({"error": "手机号已被注册"}), 400

        # Insert the new account into the database
        createtime = datetime.now()
        cursor.execute("INSERT INTO accounts (phone, passcode, name, imageurl, createtime) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                       (phone, passcode, name, imageurl, createtime))
        new_user_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Return success response
        return jsonify({"success": True, "message": "创建账号成功!", "id": new_user_id}), 201

    except Exception as e:
        flask_app.logger.info(
            f"Error registering user: {str(e)}", exc_info=True)
        return jsonify({"error": "创建失败！"}), 500


@flask_app.route('/api/signin', methods=['POST'])
def sign_in():
    phone = request.json['phone']
    passcode = request.json['passcode']

    conn = get_db()  # Connection details
    cursor = conn.cursor()

    # Fetch the hashed passcode and other details from the database
    cursor.execute(
        "SELECT id, phone, passcode, createtime, name, imageurl FROM accounts WHERE phone = %s", (phone,))
    result = cursor.fetchone()

    if result:
        id, phone, hashed_passcode, createtime, name, imageurl = result
        # Verify the hashed passcode
        if bcrypt.checkpw(passcode.encode('utf-8'), hashed_passcode.encode('utf-8')):

            # Update the last_seen timestamp to the current time
            cursor.execute(
                "UPDATE accounts SET last_seen=NOW() WHERE id=%s", (id,))
            conn.commit()

            return jsonify(success=True, user={
                "id": id,
                "phone": phone,
                # Format to a string representation
                "createtime": createtime.strftime('%Y-%m-%d %H:%M:%S'),
                "name": name,
                "imageurl": imageurl
            }), 200
        else:
            return jsonify(success=False, message='密码不正确'), 401
    else:
        return jsonify(success=False, message='电话号码不正确'), 404


@flask_app.route('/api/usersstatus', methods=['POST'])
def users_status():
    # Expecting a list of phone numbers from the frontend
    phone_numbers = request.json['phone_numbers']

    if not phone_numbers:  # Check if phone_numbers list is empty
        return jsonify({}), 200  # Return an empty JSON

    conn = get_db()
    cursor = conn.cursor()

    # Use the IN clause to match multiple phone numbers
    placeholders = ', '.join(['%s'] * len(phone_numbers))
    query = f"SELECT phone, last_seen FROM accounts WHERE phone IN ({placeholders})"
    cursor.execute(query, tuple(phone_numbers))
    results = cursor.fetchall()

    online_statuses = {}
    for phone, last_seen in results:
        is_online = False
        if last_seen:
            time_diff = datetime.now() - last_seen
            is_online = time_diff.total_seconds() < 10*60
        online_statuses[phone] = is_online

    return jsonify(online_statuses), 200


@flask_app.route("/api/mycaregiver/<phone>", methods=["GET"])
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
        flask_app.logger.error(
            f"Error fetching caregivers for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregivers"}), 500


@flask_app.route("/api/mycaregiver/<int:id>", methods=["PUT"])
def update_caregiver(id):
    flask_app.logger.debug(f"Entering update_caregiver for id {id}")
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

        flask_app.logger.debug(f"Serialized location: {json.dumps(value)}")
        flask_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE caregivers SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + f" WHERE id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        flask_app.logger.info(f"Received data: {data}")
        flask_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        flask_app.logger.error(
            f"Error updating caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update caregiver"}), 500


@flask_app.route('/api/all_caregivers', methods=['GET'])
def get_all_caregivers():
    flask_app.logger.info(
        "---------------Entering GET /api/all_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch caregivers from the database
        cursor.execute("SELECT * FROM caregivers ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning("No caregivers found in the database")
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
                "location": row["location"],
                "hourlycharge": row["hourlycharge"]
            }
            for row in rows
        ]

        flask_app.logger.debug("Successfully processed all caregivers data")

        response = make_response(jsonify(caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        flask_app.logger.error("Error fetching all caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch all caregivers"}), 500


@flask_app.route('/api/upload', methods=['POST'])
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
            response = s3.upload_file(
                tmp_filepath, 'alex-chen-images', filename)
            url = f"https://alex-chen-images.s3.ap-east-1.amazonaws.com/{filename}"
            # Cleanup temp file
            os.remove(tmp_filepath)
            return jsonify({"url": url})
    except Exception as e:
        # You can log the exception for debugging
        logger.error("File upload failed", exc_info=True)
        return jsonify({"error": "File upload failed"}), 500


@flask_app.teardown_appcontext
def close_db(error):
    # If this request used the database, close the used connection
    db = g.pop('db', None)

    if db is not None:
        db_pool.putconn(db)


@flask_app.route("/api/all_caregivers/<int:caregiver_id>", methods=["GET"])
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
            "location": row["location"],
            "hourlycharge": row["hourlycharge"]
        }

        return jsonify(caregiver)
    except Exception as e:
        logger.error(
            f"Error fetching caregiver detail for id {caregiver_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver detail"}), 500


@flask_app.route("/api/all_caregivers", methods=["POST"])
def add_caregiver():
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the mandatory columns and values for the INSERT query
        mandatory_columns = ["name", "phone",
                             "imageurl", "location", "hourlycharge"]
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
            "location": data["location"],
            "hourlycharge": data["hourlycharge"]
        }
        return jsonify(new_caregiver), 201

    except Exception as e:
        logger.error(f"Error adding caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver"}), 500

@flask_app.route("/api/caregiver_schedule", methods=["POST"])
def add_caregiver_schedule():
    try:
        data = request.get_json()

        # Log the received data for debugging
        flask_app.logger.debug("Received data caregiver_schedule: %s", data)

        # Validate that careneeder_id is provided
        if "caregiver_id" not in data:
            return jsonify({"error": "caregiver_id is required"}), 400

        # Define the columns for the INSERT query
        columns = ["scheduletype", "totalhours", "frequency",
                   "startdate", "selectedtimeslots", "durationdays", "caregiver_id"]

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
        insert_query = f"INSERT INTO caregiverschedule ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

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
        flask_app.logger.error(
            f"Error adding schedule: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add schedule"}), 500
    finally:
        if conn:
            conn.close()    

@flask_app.route('/api/all_caregiverschedule', methods=['GET'])
def get_all_caregiverschedule():
    flask_app.logger.info("Entering GET /api/all_caregiverschedule request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneederschedule data from the database
        cursor.execute("SELECT * FROM caregiverschedule ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} caregiverschedule records from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning(
                "No caregiverschedule records found in the database")
            return jsonify({"error": "No caregiverschedule data available"}), 404

        # Format the data for JSON

        caregiverschedule = [dict(row) for row in rows]

        flask_app.logger.debug(
            "Successfully processed all caregiverschedule data")

        response = make_response(jsonify(caregiverschedule))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        flask_app.logger.error(
            "Error fetching all caregiverschedule", exc_info=True)
        return jsonify({"error": "Failed to fetch all caregiverschedule"}), 500        
        

@flask_app.route("/api/caregiver_ads", methods=["POST"])
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
        flask_app.logger.error(
            f"Error adding caregiver ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver ad"}), 500
    finally:
        if conn:
            conn.close()


@flask_app.route("/api/all_caregiverads", methods=["GET"])
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

        flask_app.logger.debug(
            f"Fetched {len(rows)} caregiverads records from the database")

        # Check the data type of the first row for debugging
        if rows:
            flask_app.logger.debug(f"First row data type: {type(rows[0])}")

        if not rows:
            flask_app.logger.warning(
                "No caregiverads records found in the database")
            return jsonify({"error": "No caregiverads data available"}), 404

        caregiverads = [dict(row) for row in rows]

        flask_app.logger.debug("Successfully processed all caregiverads data")

        response = make_response(jsonify(caregiverads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        flask_app.logger.error(
            f"Error fetching caregiver ads: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver ads"}), 500

    finally:
        if conn:
            conn.close()


@flask_app.route("/api/all_careneeders", methods=["POST"])
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
        mandatory_columns = ["name", "phone", "location", "hourlycharge"]
        values = [data[field] if field != 'location' else json.dumps(
            data[field]) for field in mandatory_columns]

        # Define optional fields and include them in columns and values if they are present
        optional_fields = [
            "imageurl", "live_in_care", "live_out_care", "domestic_work", "meal_preparation",
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
            "location": data["location"],
            "hourlycharge": data["hourlycharge"]
        }

        # Include optional fields in the return object if they exist
        for field in optional_fields:
            new_careneeder[field] = data.get(field, None)

        return jsonify(new_careneeder), 201

    except Exception as e:  # Could also catch specific exceptions like psycopg2.DatabaseError
        if conn:
            conn.rollback()  # Rolling back in case of an error
        flask_app.logger.error(
            f"Error adding careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add careneeder"}), 500
    finally:
        if conn:
            conn.close()  # Ensure that the connection is closed or returned to the pool


@flask_app.route('/api/all_careneeders', methods=['GET'])
def get_all_careneeders():
    flask_app.logger.info(
        "---------------Entering GET /api/all_careneeders request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneeders from the database
        cursor.execute("SELECT * FROM careneeder ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} careneeders from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning("No careneeders found in the database")
            return jsonify({"error": "Problem of fetching careneeders"}), 404

        # Directly convert the rows into JSON
        careneeders = [dict(row) for row in rows]

        # Format the data for JSON
        careneeders = [
            {
                "id": row["id"],
                "name": row["name"],
                "phone": row["phone"],
                "hourlycharge": row["hourlycharge"],
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

        flask_app.logger.debug("Successfully processed all careneeders data")

        response = make_response(jsonify(careneeders))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        flask_app.logger.error("Error fetching all careneeders", exc_info=True)
        return jsonify({"error": "Failed to fetch all careneeders"}), 500


@flask_app.route("/api/all_careneeders/<int:careneeder_id>", methods=["GET"])
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
            "hourlycharge": row["hourlycharge"],
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


@flask_app.route("/api/mycareneeder/<phone>", methods=["GET"])
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
                "hourlycharge": row["hourlycharge"],
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
        flask_app.logger.error(
            f"Error fetching careneeders for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeders"}), 500


@flask_app.route("/api/mycaregiver/<int:id>/ad", methods=["PUT"])
def update_caregiver_ad(id):
    flask_app.logger.debug(f"Entering update_caregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        flask_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE caregiverads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE caregiver_id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        flask_app.logger.info(f"Received data: {data}")
        flask_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        flask_app.logger.error(
            f"Error updating caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update caregiver"}), 500


@flask_app.route("/api/careneeder_schedule", methods=["POST"])
def add_schedule():
    try:
        data = request.get_json()

        # Log the received data for debugging
        flask_app.logger.debug("Received data: %s", data)

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
        flask_app.logger.error(
            f"Error adding schedule: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add schedule"}), 500
    finally:
        if conn:
            conn.close()


@flask_app.route("/api/mycareneeder/<int:id>/ad", methods=["PUT"])
def update_careneeder_ad(id):
    flask_app.logger.debug(f"Entering update_careneeder for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        flask_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE careneederads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE careneeder_id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        flask_app.logger.info(f"Received data: {data}")
        flask_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        flask_app.logger.error(
            f"Error updating careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update careneeder"}), 500


@flask_app.route("/api/careneeder_ads", methods=["POST"])
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
        flask_app.logger.error(
            f"Error adding careneeder ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add careneeder ad"}), 500
    finally:
        if conn:
            conn.close()


@flask_app.route('/api/all_careneederschedule', methods=['GET'])
def get_all_careneederschedule():
    flask_app.logger.info("Entering GET /api/all_careneederschedule request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneederschedule data from the database
        cursor.execute("SELECT * FROM careneederschedule ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} careneederschedule records from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning(
                "No careneederschedule records found in the database")
            return jsonify({"error": "No careneederschedule data available"}), 404

        # Format the data for JSON

        careneederschedule = [dict(row) for row in rows]

        flask_app.logger.debug(
            "Successfully processed all careneederschedule data")

        response = make_response(jsonify(careneederschedule))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        flask_app.logger.error(
            "Error fetching all careneederschedule", exc_info=True)
        return jsonify({"error": "Failed to fetch all careneederschedule"}), 500


@flask_app.route("/api/all_careneederads", methods=["GET"])
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

        flask_app.logger.debug(
            f"Fetched {len(rows)} careneederads records from the database")

        # Check the data type of the first row for debugging
        if rows:
            flask_app.logger.debug(f"First row data type: {type(rows[0])}")

        if not rows:
            flask_app.logger.warning(
                "No careneederads records found in the database")
            return jsonify({"error": "No careneederads data available"}), 404

        careneederads = [dict(row) for row in rows]

        flask_app.logger.debug("Successfully processed all careneederads data")

        response = make_response(jsonify(careneederads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        flask_app.logger.error(
            f"Error fetching careneeder ads: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeder ads"}), 500

    finally:
        if conn:
            conn.close()


@flask_app.route("/api/animalcaregiver_details", methods=["POST"])
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
        flask_app.logger.error(
            f"Error adding animalcaregiver detail: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcaregiver detail"}), 500
    finally:
        if conn:
            conn.close()


@flask_app.route("/api/all_animalcaregivers", methods=["POST"])
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


@flask_app.route("/api/animalcaregiver_ads", methods=["POST"])
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


@flask_app.route('/api/all_animalcaregivers', methods=['GET'])
def get_all_animal_caregivers():
    flask_app.logger.info(
        "---------------Entering GET /api/all_animal_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcaregiverform ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} animal caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning(
                "No animal caregivers found in the database")
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

        flask_app.logger.debug(
            "Successfully processed all animal caregivers data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        flask_app.logger.error(
            "Error fetching all animal caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal caregivers"}), 500


@flask_app.route('/api/all_animal_caregivers_details', methods=['GET'])
def get_all_animal_caregivers_details():
    flask_app.logger.info(
        "---------------Entering GET /api/all_animal_caregivers details request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcaregiver ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} animal caregivers details from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning(
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

        flask_app.logger.debug(
            "Successfully processed all animal caregivers details data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        flask_app.logger.error(
            "Error fetching all animal caregivers details", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal caregivers details"}), 500


@flask_app.route('/api/all_animal_caregiver_ads', methods=['GET'])
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


@flask_app.route("/api/all_animalcaregiverform/<int:animalcaregiverform_id>", methods=["GET"])
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


@flask_app.route("/api/myanimalcaregiverform/<phone>", methods=["GET"])
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
        flask_app.logger.error(
            f"Error fetching animal caregiver forms for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal caregiver forms"}), 500


@flask_app.route("/api/myanimalcaregiver/<int:id>/ad", methods=["PUT"])
def update_animalcaregiver_ad(id):
    flask_app.logger.debug(f"Entering update_animalcaregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        flask_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE animalcaregiverads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE animalcaregiverid = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        flask_app.logger.info(f"Received data: {data}")
        flask_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        flask_app.logger.error(
            f"Error updating animal caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update animal caregiver"}), 500


@flask_app.route("/api/all_animalcareneeders", methods=["POST"])
def add_animalcareneeder():
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
        insert_query = f"INSERT INTO animalcareneederform ({', '.join(mandatory_columns)}) VALUES ({', '.join(['%s'] * len(mandatory_columns))}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_animalcareneeder_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Return the newly created caregiver data with the assigned ID
        # imageUrl is possibly from const [imageUrl, setImageUrl] = useState<string | null>(null) in CaregiverForm.tsx
        new_animalcareneederform = {
            "id": new_animalcareneeder_id,
            "name": data["name"],
            "phone": data["phone"],
            "age": data["age"],
            "education": data["education"],
            "gender": data["gender"],
            "years_of_experience": data["years_of_experience"],
            "imageurl": data["imageurl"],
            "location": data["location"]
        }
        return jsonify(new_animalcareneederform), 201

    except Exception as e:
        logger.error(
            f"Error adding animalcareneederform: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcareneederform"}), 500


@flask_app.route("/api/animalcareneeder_details", methods=["POST"])
def add_animalcareneeder_detail():
    conn = None
    try:
        data = request.get_json()
        print("Received data:", data)

        # Define the columns for the INSERT query
        columns = ["\"animalcareneederid\"", "\"selectedservices\"",
                   "\"selectedanimals\"", "\"hourlycharge\""]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in ["animalcareneederid", "selectedservices", "selectedanimals", "hourlycharge"]:
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
        insert_query = f'INSERT INTO animalcareneeder ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id'

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
        for column in ["animalcareneederid", "selectedservices", "selectedanimals", "hourlycharge"]:
            if column in data:
                new_detail[column] = data[column]

        return jsonify(new_detail), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        flask_app.logger.error(
            f"Error adding animalcareneeder detail: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcareneeder detail"}), 500
    finally:
        if conn:
            conn.close()


@flask_app.route("/api/animalcareneeder_ads", methods=["POST"])
def add_animal_careneeder_ad():
    conn = None
    try:
        data = request.get_json()

        # Validate if "animalcaregiverid", "title", and "description" are present in data
        if not all(key in data for key in ["animalcareneederid", "title", "description"]):
            return jsonify({"error": "Required fields are missing"}), 400

        # Define the columns for the INSERT query
        columns = ["title", "description", "animalcareneederid"]

        # Initialize values list
        values = [data["title"], data["description"],
                  data["animalcareneederid"]]

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO animalcareneederads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_animalcareneeder_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the ad interface
        new_ad = {
            "id": new_animalcareneeder_id,
            "title": data["title"],
            "description": data["description"],
            "animalcareneederid": data["animalcareneederid"]
        }

        return jsonify(new_ad), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        logger.error(
            f"Error adding animal careneeder ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animal careneeder ad"}), 500
    finally:
        if conn:
            conn.close()


@flask_app.route('/api/all_animalcareneeders', methods=['GET'])
def get_all_animal_careneeders():
    flask_app.logger.info(
        "---------------Entering GET /api/all_animal_careneeders request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcareneederform ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} animal careneeders from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning(
                "No animal careneeders found in the database")
            return jsonify({"error": "Problem of fetching animal careneeders"}), 404

        # Directly convert the rows into JSON
        animal_careneeders = [dict(row) for row in rows]

        # Format the data for JSON
        animal_careneeders = [
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

        flask_app.logger.debug(
            "Successfully processed all animal careneeders data")

        response = make_response(jsonify(animal_careneeders))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        flask_app.logger.error(
            "Error fetching all animal careneeders", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal careneeders"}), 500


@flask_app.route('/api/all_animal_careneeders_details', methods=['GET'])
def get_all_animal_careneeders_details():
    flask_app.logger.info(
        "---------------Entering GET /api/all_animal_careneeders details request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcareneeder ORDER BY id DESC")
        rows = cursor.fetchall()
        flask_app.logger.debug(
            f"Fetched {len(rows)} animal careneeders details from the database")

        # Close the connection
        cursor.close()

        if not rows:
            flask_app.logger.warning(
                "No animal careneeders details found in the database")
            return jsonify({"error": "Problem fetching animal careneeders details"}), 404

        # Directly convert the rows into JSON
        animal_caregivers = [
            {
                "id": row["id"],
                "animalcareneederid": row["animalcareneederid"],
                "selectedservices": row["selectedservices"],
                "selectedanimals": row["selectedanimals"],
                "hourlycharge": row["hourlycharge"]
            }
            for row in rows
        ]

        flask_app.logger.debug(
            "Successfully processed all animal careneeders details data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        flask_app.logger.error(
            "Error fetching all animal careneeders details", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal careneeders details"}), 500


@flask_app.route('/api/all_animal_careneeder_ads', methods=['GET'])
def get_all_animal_careneeder_ads():
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Using the correct table name
        cursor.execute("SELECT * FROM animalcareneederads ORDER BY id DESC")
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return jsonify({"error": "No animal careneeder ads found"}), 404

        animal_careneeder_ads = [
            {
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "animalcareneederid": row["animalcareneederid"]
            }
            for row in rows
        ]

        response = make_response(jsonify(animal_careneeder_ads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        return jsonify({"error": "Failed to fetch animal careneeder ads"}), 500


@flask_app.route("/api/myanimalcareneeder/<int:id>/ad", methods=["PUT"])
def update_animalcareneeder_ad(id):
    flask_app.logger.debug(f"Entering update_animalcareneeder for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        flask_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE animalcareneederads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE animalcareneederid = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        flask_app.logger.info(f"Received data: {data}")
        flask_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        flask_app.logger.error(
            f"Error updating animal careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update animal careneeder"}), 500


@flask_app.route("/api/all_animalcareneederform/<int:animalcareneederform_id>", methods=["GET"])
def get_animalcareneederform_detail(animalcareneederform_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the specific record from the animalcareneederform table using the id
        cursor.execute(
            "SELECT * FROM animalcareneederform WHERE id = %s", (animalcareneederform_id,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        # Check if a record with the given id exists
        if not row:
            return jsonify({"error": "Animal Careneeder Form not found"}), 404

        # Format the data for JSON (update these keys as needed)
        animalcareneederform = {
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

        return jsonify(animalcareneederform)
    except Exception as e:
        logger.error(
            f"Error fetching animal careneeder form detail for id {animalcareneederform_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal careneeder form detail"}), 500


@flask_app.route("/api/myanimalcareneederform/<phone>", methods=["GET"])
def get_myanimalcareneederform(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the records related to the phone number from the animalcareneederform table
        cursor.execute(
            "SELECT * FROM animalcareneederform WHERE phone = %s ORDER BY id DESC", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Animal Careneeder Forms not found"}), 404

        animalcareneederforms = [
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

        return jsonify(animalcareneederforms)
    except Exception as e:
        flask_app.logger.error(
            f"Error fetching animal careneeder forms for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal careneeder forms"}), 500


# Chatwindow endpoint for messages

@flask_app.route("/api/handle_message", methods=['POST'])
def handle_message():
    try:
        flask_app.logger.info("Received a request to handle_message")

        # Validate input data
        if not request.is_json:
            return jsonify(success=False, message="Invalid data format"), 400

        data = request.json
        flask_app.logger.info(f"Input Data: {data}")

        # Define the mandatory fields required
        mandatory_fields = ["sender_id", "recipient_id", "content", "ad_id"]

        # Check if necessary data is provided
        if not all(data.get(field) for field in mandatory_fields):
            return jsonify(success=False, message="Missing required data"), 400

        # Get current timestamp
        createtime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Connect to the database
        conn = get_db()
        cur = conn.cursor()

        # Step 1: Find or Create Conversation
        query = """SELECT id FROM conversations WHERE (user1_phone = %s AND user2_phone = %s) 
                   OR (user1_phone = %s AND user2_phone = %s)"""
        cur.execute(query, (data["sender_id"], data["recipient_id"],
                    data["recipient_id"], data["sender_id"]))
        conversation = cur.fetchone()

        if conversation is None:
            # Create a new conversation
            cur.execute(
                "INSERT INTO conversations (user1_phone, user2_phone) VALUES (%s, %s) RETURNING id",
                (data["sender_id"], data["recipient_id"])
            )
            conversation_id = cur.fetchone()[0]
        else:
            conversation_id = conversation[0]

        # Step 2: Insert the message with conversation_id
        query = """INSERT INTO messages (sender_id, recipient_id, content, ad_id, ad_type, createtime, conversation_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id"""

        values = [
            data["sender_id"],
            data["recipient_id"],
            data["content"],
            data["ad_id"],  # This field is now mandatory
            data.get("ad_type", None),  # Optional field
            createtime,
            conversation_id
        ]

        # Execute the query
        cur.execute(query, values)
        new_message_id = cur.fetchone()[0]
        conn.commit()
        cur.close()

        flask_app.logger.info("Database query executed successfully")

        # Create the returned object based on the interface
        new_messages = {
            "id": new_message_id,
            "conversation_id": conversation_id
        }

        # Include columns in the return object if they exist
        for column in mandatory_fields + ["ad_type", "createtime"]:
            if column in data:
                new_messages[column] = data[column]

        return jsonify(new_messages), 201

    except Exception as e:
        traceback_str = traceback.format_exc()
        flask_app.logger.error(
            f"Error occurred: {e}\nTraceback:\n{traceback_str}")
        return jsonify(success=False, message="An error occurred while processing the request"), 500


@flask_app.route("/api/fetch_messages", methods=['GET'])
def fetch_messages_chatwindow():
    sender_id = request.args.get('sender_id')
    recipient_id = request.args.get('recipient_id')
    ad_id = request.args.get('ad_id')
    ad_type = request.args.get('ad_type')

    if not sender_id or not recipient_id or not ad_id or not ad_type:
        return jsonify({'error': 'sender_id, recipient_id, ad_id, and ad_type are required'}), 400

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=DictCursor)

        query = """SELECT * FROM messages WHERE ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s)) 
           AND ad_id = %s AND ad_type = %s ORDER BY createtime ASC"""

        cursor.execute(
            query, (sender_id, recipient_id, recipient_id, sender_id, ad_id, ad_type))

        messages = cursor.fetchall()

        if not messages:
            return jsonify([]), 200  # Empty list but still a valid request

        # Convert to JSON objects
        messages_json = []
        for message in messages:
            message_obj = {
                "id": message[0],
                "sender_id": message[1],
                "recipient_id": message[2],
                "content": message[3],
                "createtime": message[4],
                "conversation_id": message[5],
                "ad_id": ad_id,
                "ad_type": ad_type
            }
            messages_json.append(message_obj)

        response = make_response(jsonify(messages_json))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        flask_app.logger.error(f"Error occurred: {e}")
        return jsonify({'error': 'An error occurred while processing the request'}), 500

    finally:
        if cursor:
            cursor.close()


@flask_app.route('/api/list_conversations', methods=['GET'])
def list_conversations():
    try:
        user_phone = request.args.get('user_phone')

        conn = get_db()
        cur = conn.cursor()

        # Adjusted SQL Query
        query = """
        SELECT 
            c.id, 
            CASE 
                WHEN c.user1_phone = %s THEN c.user2_phone 
                ELSE c.user1_phone 
            END AS other_user_phone,
            a.name, 
            a.imageurl, 
            m.content AS lastMessage, 
            m.createtime AS timestamp,
            m.ad_id,
            m.ad_type 
        FROM conversations c
        LEFT JOIN accounts a ON a.phone = CASE 
                WHEN c.user1_phone = %s THEN c.user2_phone 
                ELSE c.user1_phone 
            END
        LEFT JOIN (
            SELECT content, createtime, conversation_id, ad_id, ad_type
            FROM messages 
            WHERE (conversation_id, createtime, ad_type) IN (
                SELECT conversation_id, MAX(createtime), ad_type 
                FROM messages 
                WHERE sender_id = %s OR recipient_id = %s
                GROUP BY conversation_id, ad_id, ad_type
            )
        ) m ON m.conversation_id = c.id
        WHERE c.user1_phone = %s OR c.user2_phone = %s 
        ORDER BY m.createtime DESC;
        """
        cur.execute(query, (user_phone, user_phone, user_phone,
                    user_phone, user_phone, user_phone))

        conversations = cur.fetchall()
        cur.close()

        # Serialize and return
        conversations_list = [{
            "conversation_id": row[0],
            "other_user_phone": row[1],
            "name": row[2],
            "profileImage": row[3],
            "lastMessage": row[4],
            "timestamp": str(row[5]),  # Convert datetime object to string
            "ad_id": row[6],
            "ad_type": row[7]
        } for row in conversations]

        response = make_response(
            jsonify({"conversations": conversations_list}))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        traceback_str = traceback.format_exc()
        flask_app.logger.error(
            f"Error occurred: {e}\nTraceback:\n{traceback_str}")
        return jsonify(success=False, message="An error occurred while processing the request"), 500


# New endpoint for fetching messages based on conversation_id
@flask_app.route('/api/fetch_messages_chat_conversation', methods=['GET'])
def fetch_messages_chat_conversation():
    conversation_id = request.args.get('conversation_id')
    ad_id = request.args.get('ad_id')
    if not conversation_id:
        return jsonify({'error': 'conversation_id is required'}), 400

        # Convert to integer to prevent SQL injection
    try:
        conversation_id = int(conversation_id)
        ad_id = int(ad_id)
    except ValueError:
        return jsonify({'error': 'Invalid conversation_id or ad_id'}), 400

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=DictCursor)

        cursor.execute(
            "SELECT * FROM messages WHERE conversation_id = %s AND ad_id = %s", (conversation_id, ad_id))

        messages = cursor.fetchall()

        if not messages:
            return jsonify([]), 200  # Empty list but still a valid request

        # Convert to JSON objects
        messages_json = []
        for message in messages:
            message_obj = {
                "id": message[0],
                "sender_id": message[1],
                "recipient_id": message[2],
                "content": message[3],
                "createtime": message[4],
                "conversation_id": message[5],
                "ad_id": message[6]
            }
            messages_json.append(message_obj)

        response = make_response(jsonify(messages_json))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        flask_app.logger.error(f"Error occurred: {e}")
        return jsonify({'error': 'An error occurred while processing the request'}), 500

    finally:
        if cursor:
            cursor.close()


# fetch the accounts data to the frontend
@flask_app.route("/api/account/<phone>", methods=["GET"])
def get_account(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the account related to the phone number
        cursor.execute(
            "SELECT * FROM accounts WHERE phone = %s LIMIT 1", (phone,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        if not row:
            return jsonify({"error": "Account not found"}), 404

        account = {
            "id": row["id"],
            "phone": row["phone"],
            "passcode": row["passcode"],
            "createtime": row["createtime"],
            "name": row["name"],
            "imageurl": row["imageurl"]
        }
        print(account)

        return jsonify(account)
    except Exception as e:
        flask_app.logger.error(
            f"Error fetching account for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch account"}), 500


if __name__ == "__main__":
    flask_app.run(debug=True)
