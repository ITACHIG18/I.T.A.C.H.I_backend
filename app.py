
import os
import json
import uuid

from datetime import datetime, timedelta, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import fitz

from dotenv import load_dotenv
from openai import OpenAI
import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_THIS_SECRET_BEFORE_DEPLOYING"
)

JWT_EXPIRATION_MINUTES = int(
    os.getenv(
        "JWT_EXPIRATION_MINUTES",
        "1440"
    )
)


# ============================================================
# MYSQL CONFIGURATION
# ============================================================

DB_HOST = os.getenv(
    "DB_HOST",
    "127.0.0.1"
)

DB_PORT = int(
    os.getenv(
        "DB_PORT",
        "3306"
    )
)

DB_NAME = os.getenv(
    "DB_NAME",
    "studymate_db"
)

DB_USER = os.getenv(
    "DB_USER",
    "root"
)

DB_PASSWORD = os.getenv(
    "DB_PASSWORD",
    ""
)


# ============================================================
# OPENAI CLIENT
# ============================================================

client = None

if OPENAI_API_KEY:

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

CORS(app)


# ============================================================
# UPLOAD CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config[
    "UPLOAD_FOLDER"
] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "pdf"
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    try:

        connection = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            use_pure=True
        )

        return connection

    except Error as error:

        print(
            "MySQL connection error:",
            error
        )

        return None


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

def database_is_available():

    connection = get_db_connection()

    if connection is None:

        return False

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1"
        )

        cursor.fetchone()

        cursor.close()

        connection.close()

        return True

    except Error as error:

        print(
            "Database health check error:",
            error
        )

        try:
            connection.close()
        except Exception:
            pass

        return False


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
    )


# ============================================================
# CREATE JWT TOKEN
# ============================================================

def create_access_token(user):

    now = datetime.now(
        timezone.utc
    )

    expiration = now + timedelta(
        minutes=JWT_EXPIRATION_MINUTES
    )

    payload = {

        "sub":
            str(user["id"]),

        "email":
            user["email"],

        "name":
            user["name"],

        "iat":
            now,

        "exp":
            expiration
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm="HS256"
    )

    return token


# ============================================================
# FIND USER BY ID
# ============================================================

def get_user_by_id(user_id):

    connection = get_db_connection()

    if connection is None:

        return None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                name,
                email,
                password_hash,
                email_verified,
                verification_code,
                verification_expires,
                created_at
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        cursor.close()

        connection.close()

        return user

    except Error as error:

        print(
            "Find user error:",
            error
        )

        try:
            connection.close()
        except Exception:
            pass

        return None


# ============================================================
# FIND USER BY EMAIL
# ============================================================

def get_user_by_email(email):

    connection = get_db_connection()

    if connection is None:

        return None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                name,
                email,
                password_hash,
                email_verified,
                verification_code,
                verification_expires,
                created_at
            FROM users
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()

        connection.close()

        return user

    except Error as error:

        print(
            "Find user by email error:",
            error
        )

        try:
            connection.close()
        except Exception:
            pass

        return None


# ============================================================
# SAFE USER RESPONSE
# ============================================================

def public_user(user):

    created_at = user.get(
        "created_at"
    )

    if isinstance(
        created_at,
        datetime
    ):

        created_at = created_at.isoformat()

    return {

        "id":
            user["id"],

        "name":
            user["name"],

        "email":
            user["email"],

        "email_verified":
            True,

        "created_at":
            created_at
    }


# ============================================================
# VERIFY JWT TOKEN
# ============================================================

def get_current_user():

    authorization = request.headers.get(
        "Authorization"
    )

    if not authorization:

        return None, (
            jsonify({
                "error":
                    "Authorization token is required."
            }),
            401
        )

    parts = authorization.split()

    if len(parts) != 2:

        return None, (
            jsonify({
                "error":
                    "Invalid authorization header."
            }),
            401
        )

    if parts[0].lower() != "bearer":

        return None, (
            jsonify({
                "error":
                    "Authorization must use Bearer token."
            }),
            401
        )

    token = parts[1]

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        user_id = payload.get(
            "sub"
        )

        if not user_id:

            return None, (
                jsonify({
                    "error":
                        "Invalid token."
                }),
                401
            )

        user = get_user_by_id(
            user_id
        )

        if not user:

            return None, (
                jsonify({
                    "error":
                        "User account was not found."
                }),
                401
            )

        return user, None

    except jwt.ExpiredSignatureError:

        return None, (
            jsonify({
                "error":
                    "Your session has expired. Please log in again."
            }),
            401
        )

    except jwt.InvalidTokenError:

        return None, (
            jsonify({
                "error":
                    "Invalid or expired authentication token."
            }),
            401
        )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "message":
            "StudyMate backend is running.",

        "status":
            "online",

        "service":
            "StudyMate API"

    }), 200


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    database_status = database_is_available()

    return jsonify({

        "status":
            "ok",

        "message":
            "StudyMate API is working.",

        "database":
            "connected"
            if database_status
            else "disconnected"

    }), 200


# ============================================================
# AUTH — REGISTER
# ============================================================

@app.route(
    "/api/auth/register",
    methods=["POST"]
)
def register():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No registration data was provided."
        }), 400

    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    if not name:

        return jsonify({
            "error":
                "Name is required."
        }), 400

    if len(name) < 2:

        return jsonify({
            "error":
                "Name must contain at least 2 characters."
        }), 400

    if not email:

        return jsonify({
            "error":
                "Email is required."
        }), 400

    if "@" not in email or "." not in email:

        return jsonify({
            "error":
                "Please enter a valid email address."
        }), 400

    if not password:

        return jsonify({
            "error":
                "Password is required."
        }), 400

    if len(password) < 8:

        return jsonify({
            "error":
                "Password must be at least 8 characters."
        }), 400

    # --------------------------------------------------------
    # CHECK DATABASE
    # --------------------------------------------------------

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        existing_user = cursor.fetchone()

        # ----------------------------------------------------
        # ACCOUNT ALREADY EXISTS
        # ----------------------------------------------------

        if existing_user:

            cursor.close()
            connection.close()

            return jsonify({
                "error":
                    "An account with this email already exists."
            }), 409

        # ----------------------------------------------------
        # CREATE ACCOUNT
        # ----------------------------------------------------

        password_hash = generate_password_hash(
            password
        )

        cursor.execute(
            """
            INSERT INTO users (
                name,
                email,
                password_hash,
                email_verified,
                verification_code,
                verification_expires
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                name,
                email,
                password_hash,
                True,
                None,
                None
            )
        )

        user_id = cursor.lastrowid

        connection.commit()

        cursor.close()
        connection.close()

    except Error as error:

        print(
            "Registration database error:",
            error
        )

        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass

        return jsonify({
            "error":
                "Something went wrong while creating your account."
        }), 500

    # --------------------------------------------------------
    # GET CREATED USER
    # --------------------------------------------------------

    user = get_user_by_id(
        user_id
    )

    if not user:

        return jsonify({
            "error":
                "Account was created, but the user could not be loaded."
        }), 500

    # --------------------------------------------------------
    # CREATE JWT
    # --------------------------------------------------------

    token = create_access_token(
        user
    )

    return jsonify({

        "message":
            "Account created successfully.",

        "token":
            token,

        "user":
            public_user(
                user
            )

    }), 201


# ============================================================
# AUTH — LOGIN
# ============================================================

@app.route(
    "/api/auth/login",
    methods=["POST"]
)
def login():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No login data was provided."
        }), 400

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    if not email:

        return jsonify({
            "error":
                "Email is required."
        }), 400

    if not password:

        return jsonify({
            "error":
                "Password is required."
        }), 400

    user = get_user_by_email(
        email
    )

    if not user:

        return jsonify({
            "error":
                "Invalid email or password."
        }), 401

    if not check_password_hash(
        user["password_hash"],
        password
    ):

        return jsonify({
            "error":
                "Invalid email or password."
        }), 401

    # --------------------------------------------------------
    # CREATE JWT
    # --------------------------------------------------------

    token = create_access_token(
        user
    )

    return jsonify({

        "message":
            "Login successful.",

        "token":
            token,

        "user":
            public_user(
                user
            )

    }), 200


# ============================================================
# AUTH — CURRENT USER
# ============================================================

@app.route(
    "/api/auth/me",
    methods=["GET"]
)
def current_user():

    user, error_response = (
        get_current_user()
    )

    if error_response:

        return error_response

    return jsonify({

        "user":
            public_user(
                user
            )

    }), 200


# ============================================================
# AUTH — LOGOUT
# ============================================================

@app.route(
    "/api/auth/logout",
    methods=["POST"]
)
def logout():

    return jsonify({

        "message":
            "Logged out successfully."

    }), 200


# ============================================================
# PDF UPLOAD
# ============================================================

@app.route(
    "/api/upload-pdf",
    methods=["POST"]
)
def upload_pdf():

    # --------------------------------------------------------
    # REQUIRE LOGIN
    # --------------------------------------------------------

    user, error_response = (
        get_current_user()
    )

    if error_response:

        return error_response

    if "file" not in request.files:

        return jsonify({
            "error":
                "No file was uploaded."
        }), 400

    file = request.files[
        "file"
    ]

    if file.filename == "":

        return jsonify({
            "error":
                "No file was selected."
        }), 400

    if not allowed_file(
        file.filename
    ):

        return jsonify({
            "error":
                "Only PDF files are allowed."
        }), 400

    original_filename = secure_filename(
        file.filename
    )

    unique_filename = (
        f"{uuid.uuid4().hex}_"
        f"{original_filename}"
    )

    file_path = os.path.join(
        app.config[
            "UPLOAD_FOLDER"
        ],
        unique_filename
    )

    try:

        file.save(
            file_path
        )

        document = fitz.open(
            file_path
        )

        extracted_text = ""

        for page_number, page in enumerate(
            document
        ):

            page_text = page.get_text()

            extracted_text += page_text

            if page_number < len(document) - 1:

                extracted_text += "\n\n"

        page_count = len(
            document
        )

        document.close()

        return jsonify({

            "message":
                "PDF uploaded and processed successfully.",

            "filename":
                unique_filename,

            "original_filename":
                original_filename,

            "pages":
                page_count,

            "text":
                extracted_text

        }), 200

    except Exception as error:

        print(
            "PDF processing error:",
            error
        )

        if os.path.exists(
            file_path
        ):

            try:

                os.remove(
                    file_path
                )

            except Exception:
                pass

        return jsonify({

            "error":
                "Something went wrong while processing the PDF."

        }), 500
