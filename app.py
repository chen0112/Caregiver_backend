from psycopg2.extras import DictCursor  # Assuming you are using psycopg2
from flask import Flask, g, request, jsonify
from flask_cors import CORS
import boto3
from werkzeug.utils import secure_filename
import os
from psycopg2.extras import DictCursor
import logging
from flask import make_response
import bcrypt
import json
from datetime import datetime
import traceback
from db import close_db, get_db
from caregiver import caregiver_bp
from careneeder import careneeder_bp
from animalcaregiver import animalcaregiver_bp
from animalcareneeder import animalcareneeder_bp

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


s3 = boto3.client('s3', region_name='ap-east-1')

flask_app.teardown_appcontext(close_db)


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
        mandatory_fields = ["sender_id", "recipient_id",
                            "content", "ad_id", "ably_message_id"]

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
        query = """INSERT INTO messages (sender_id, recipient_id, content, ad_id, ad_type, createtime, conversation_id, ably_message_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"""

        values = [
            data["sender_id"],
            data["recipient_id"],
            data["content"],
            data["ad_id"],  # This field is now mandatory
            data.get("ad_type", None),  # Optional field
            createtime,
            conversation_id,
            data["ably_message_id"]
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

        new_messages["ably_message_id"] = data["ably_message_id"]

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


flask_app.register_blueprint(caregiver_bp, url_prefix='/api/caregiver')

flask_app.register_blueprint(careneeder_bp, url_prefix='/api/careneeder')

flask_app.register_blueprint(
    animalcaregiver_bp, url_prefix='/api/animalcaregiver')

flask_app.register_blueprint(
    animalcareneeder_bp, url_prefix='/api/animalcareneeder')


if __name__ == "__main__":
    flask_app.run(debug=True)
