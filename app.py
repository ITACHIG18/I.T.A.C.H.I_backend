import os
import json
import uuid
import re

from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from werkzeug.security import generate_password_hash, check_password_hash

import fitz

from dotenv import load_dotenv
from google import genai
from google.genai import types

import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_THIS_SECRET_BEFORE_DEPLOYING"
)

JWT_EXPIRATION_MINUTES = int(
    os.getenv("JWT_EXPIRATION_MINUTES", "1440")
)


# ============================================================
# MYSQL CONFIGURATION
# ============================================================

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "studymate_db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )
        print("Gemini client initialized successfully.")
        print("Gemini model:", GEMINI_MODEL)

    except Exception as error:
        print(
            "Gemini client initialization error:",
            repr(error)
        )
        gemini_client = None
else:
    print("WARNING: GEMINI_API_KEY is not configured.")


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    },
    supports_credentials=True
)


# ============================================================
# PDF CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {"pdf"}

MAX_PDF_SIZE_MB = int(
    os.getenv("MAX_PDF_SIZE_MB", "25")
)

MAX_PDF_SIZE_BYTES = (
    MAX_PDF_SIZE_MB * 1024 * 1024
)

app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_SIZE_BYTES


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
            repr(error)
        )
        return None


def database_is_available():
    connection = get_db_connection()

    if connection is None:
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("SELECT 1")
        cursor.fetchone()

        return True

    except Error as error:
        print(
            "Database health check error:",
            repr(error)
        )
        return False

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# PERMANENT PDF STORAGE TABLE
# ============================================================

def initialize_pdf_storage():
    connection = get_db_connection()

    if connection is None:
        print(
            "Could not initialize PDF storage: "
            "database unavailable."
        )
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS study_materials (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                stored_filename VARCHAR(255) NOT NULL,
                file_data LONGBLOB NOT NULL,
                extracted_text LONGTEXT,
                page_count INT DEFAULT 0,
                file_size BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                INDEX idx_study_materials_user_id (user_id),

                CONSTRAINT fk_study_materials_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.commit()

        print("Permanent PDF storage table is ready.")

        return True

    except Error as error:
        print(
            "PDF storage table initialization error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return False

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# JWT
# ============================================================

def create_access_token(user):
    now = datetime.now(timezone.utc)

    expiration = now + timedelta(
        minutes=JWT_EXPIRATION_MINUTES
    )

    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "iat": now,
        "exp": expiration
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm="HS256"
    )


def get_user_by_id(user_id):
    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        return cursor.fetchone()

    except Error as error:
        print(
            "Find user error:",
            repr(error)
        )
        return None

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


def get_user_by_email(email):
    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        return cursor.fetchone()

    except Error as error:
        print(
            "Find user by email error:",
            repr(error)
        )
        return None

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass

def public_user(user):
    created_at = user.get("created_at")

    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "email_verified": True,
        "created_at": created_at
    }


def get_current_user():
    authorization = request.headers.get("Authorization")

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

    try:
        payload = jwt.decode(
            parts[1],
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        user_id = payload.get("sub")

        if not user_id:
            return None, (
                jsonify({
                    "error": "Invalid token."
                }),
                401
            )

        user = get_user_by_id(user_id)

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

    import os
import json
import uuid
import re

from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from werkzeug.security import generate_password_hash, check_password_hash

import fitz

from dotenv import load_dotenv
from google import genai
from google.genai import types

import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_THIS_SECRET_BEFORE_DEPLOYING"
)

JWT_EXPIRATION_MINUTES = int(
    os.getenv("JWT_EXPIRATION_MINUTES", "1440")
)


# ============================================================
# MYSQL CONFIGURATION
# ============================================================

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "studymate_db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )
        print("Gemini client initialized successfully.")
        print("Gemini model:", GEMINI_MODEL)

    except Exception as error:
        print(
            "Gemini client initialization error:",
            repr(error)
        )
        gemini_client = None
else:
    print("WARNING: GEMINI_API_KEY is not configured.")


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    },
    supports_credentials=True
)


# ============================================================
# PDF CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {"pdf"}

MAX_PDF_SIZE_MB = int(
    os.getenv("MAX_PDF_SIZE_MB", "25")
)

MAX_PDF_SIZE_BYTES = (
    MAX_PDF_SIZE_MB * 1024 * 1024
)

app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_SIZE_BYTES


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
            repr(error)
        )
        return None


def database_is_available():
    connection = get_db_connection()

    if connection is None:
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("SELECT 1")
        cursor.fetchone()

        return True

    except Error as error:
        print(
            "Database health check error:",
            repr(error)
        )
        return False

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# PERMANENT PDF STORAGE TABLE
# ============================================================

def initialize_pdf_storage():
    connection = get_db_connection()

    if connection is None:
        print(
            "Could not initialize PDF storage: "
            "database unavailable."
        )
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS study_materials (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                stored_filename VARCHAR(255) NOT NULL,
                file_data LONGBLOB NOT NULL,
                extracted_text LONGTEXT,
                page_count INT DEFAULT 0,
                file_size BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                INDEX idx_study_materials_user_id (user_id),

                CONSTRAINT fk_study_materials_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.commit()

        print("Permanent PDF storage table is ready.")

        return True

    except Error as error:
        print(
            "PDF storage table initialization error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return False

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# JWT
# ============================================================

def create_access_token(user):
    now = datetime.now(timezone.utc)

    expiration = now + timedelta(
        minutes=JWT_EXPIRATION_MINUTES
    )

    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "iat": now,
        "exp": expiration
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm="HS256"
    )


def get_user_by_id(user_id):
    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        return cursor.fetchone()

    except Error as error:
        print(
            "Find user error:",
            repr(error)
        )
        return None

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


def get_user_by_email(email):
    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        return cursor.fetchone()

    except Error as error:
        print(
            "Find user by email error:",
            repr(error)
        )
        return None

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

            try:
                connection.close()
            except Exception:
                pass


def public_user(user):
    created_at = user.get("created_at")

    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "email_verified": True,
        "created_at": created_at
    }


def get_current_user():
    authorization = request.headers.get("Authorization")

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

    try:
        payload = jwt.decode(
            parts[1],
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        user_id = payload.get("sub")

        if not user_id:
            return None, (
                jsonify({
                    "error": "Invalid token."
                }),
                401
            )

        user = get_user_by_id(user_id)

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
# UPLOAD PDF
# ============================================================

@app.route("/api/upload-pdf", methods=["POST"])
def upload_pdf():
    user, error_response = get_current_user()

    if error_response:
        return error_response

    if "file" not in request.files:
        return jsonify({
            "error":
                "No file was uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "error":
                "No file was selected."
        }), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error":
                "Only PDF files are allowed."
        }), 400

    original_filename = file.filename.strip()

    try:
        pdf_bytes = file.read()

        if not pdf_bytes:
            return jsonify({
                "error":
                    "The uploaded PDF is empty."
            }), 400

        file_size = len(pdf_bytes)

        if file_size > MAX_PDF_SIZE_BYTES:
            return jsonify({
                "error":
                    f"PDF files must be smaller than "
                    f"{MAX_PDF_SIZE_MB} MB."
            }), 413

        document = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        extracted_parts = []

        for page in document:
            page_text = page.get_text()

            if page_text:
                extracted_parts.append(
                    page_text
                )

        page_count = len(document)

        document.close()

        extracted_text = "\n\n".join(
            extracted_parts
        ).strip()

        if not extracted_text:
            return jsonify({
                "error":
                    "The PDF was uploaded, but no readable text was found."
            }), 400

    except Exception as error:
        print(
            "PDF processing error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Something went wrong while processing the PDF."
        }), 500

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "error":
                "The PDF was processed, but the database is unavailable."
        }), 500

    cursor = None

    try:
        cursor = connection.cursor()

        stored_filename = (
            f"{uuid.uuid4().hex}_"
            f"{original_filename}"
        )

        cursor.execute(
            """
            INSERT INTO study_materials (
                user_id,
                original_filename,
                stored_filename,
                file_data,
                extracted_text,
                page_count,
                file_size
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user["id"],
                original_filename,
                stored_filename,
                pdf_bytes,
                extracted_text,
                page_count,
                file_size
            )
        )

        pdf_id = cursor.lastrowid

        connection.commit()

        return jsonify({
            "message":
                "PDF uploaded and saved permanently.",
            "id":
                pdf_id,
            "filename":
                stored_filename,
            "original_filename":
                original_filename,
            "pages":
                page_count,
            "file_size":
                file_size,
            "text":
                extracted_text
        }), 200

    except Error as error:
        print(
            "Permanent PDF storage error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return jsonify({
            "error":
                "The PDF could not be saved permanently."
        }), 500

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# GET SAVED PDFs
# ============================================================

@app.route("/api/pdfs", methods=["GET"])
def get_saved_pdfs():
    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:
        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                original_filename,
                stored_filename,
                page_count,
                file_size,
                created_at
            FROM study_materials
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user["id"],)
        )

        rows = cursor.fetchall()

        pdfs = []

        for row in rows:
            created_at = row.get("created_at")

            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()

            pdfs.append({
                "id":
                    row["id"],
                "original_filename":
                    row["original_filename"],
                "filename":
                    row["stored_filename"],
                "pages":
                    row["page_count"],
                "file_size":
                    row["file_size"],
                "created_at":
                    created_at
            })

        return jsonify({
            "pdfs": pdfs
        }), 200

    except Error as error:
        print(
            "Get saved PDFs error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Could not load your saved PDFs."
        }), 500

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# GET SINGLE PDF
# ============================================================

@app.route("/api/pdfs/<int:pdf_id>", methods=["GET"])
def get_saved_pdf(pdf_id):
    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:
        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                original_filename,
                file_data
            FROM study_materials
            WHERE id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (
                pdf_id,
                user["id"]
            )
        )

        pdf = cursor.fetchone()

        if not pdf:
            return jsonify({
                "error":
                    "PDF not found."
            }), 404

        return send_file(
            BytesIO(pdf["file_data"]),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=pdf["original_filename"]
        )

    except Error as error:
        print(
            "Get PDF error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Could not retrieve the PDF."
        }), 500

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# GET PDF DETAILS
# ============================================================

@app.route(
    "/api/pdfs/<int:pdf_id>/details",
    methods=["GET"]
)
def get_saved_pdf_details(pdf_id):
    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:
        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                original_filename,
                stored_filename,
                extracted_text,
                page_count,
                file_size,
                created_at
            FROM study_materials
            WHERE id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (
                pdf_id,
                user["id"]
            )
        )

        pdf = cursor.fetchone()

        if not pdf:
            return jsonify({
                "error":
                    "PDF not found."
            }), 404

        created_at = pdf.get("created_at")

        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        return jsonify({
            "id":
                pdf["id"],
            "original_filename":
                pdf["original_filename"],
            "filename":
                pdf["stored_filename"],
            "text":
                pdf["extracted_text"],
            "pages":
                pdf["page_count"],
            "file_size":
                pdf["file_size"],
            "created_at":
                created_at
        }), 200

    except Error as error:
        print(
            "Get PDF details error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Could not load the PDF details."
        }), 500

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# DELETE PDF
# ============================================================

@app.route(
    "/api/pdfs/<int:pdf_id>",
    methods=["DELETE"]
)
def delete_saved_pdf(pdf_id):
    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM study_materials
            WHERE id = %s
              AND user_id = %s
            """,
            (
                pdf_id,
                user["id"]
            )
        )

        deleted_rows = cursor.rowcount

        connection.commit()

        if deleted_rows == 0:
            return jsonify({
                "error":
                    "PDF not found."
            }), 404

        return jsonify({
            "message":
                "PDF deleted successfully."
        }), 200

    except Error as error:
        print(
            "Delete saved PDF error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return jsonify({
            "error":
                "Could not delete the PDF."
        }), 500

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


    # ============================================================
# GENERATE AI STUDY NOTES
# ============================================================

@app.route(
    "/api/generate-notes",
    methods=["POST"]
)
def generate_notes():
    user, error_response = get_current_user()

    if error_response:
        return error_response

    if gemini_client is None:
        return jsonify({
            "error":
                "Gemini is not configured on the server. "
                "Please add GEMINI_API_KEY to your environment variables."
        }), 500

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error":
                "No study material was provided."
        }), 400

    text = str(
        data.get("text", "")
    ).strip()

    if not text:
        return jsonify({
            "error":
                "Study material is empty."
        }), 400

    # Keep requests within a reasonable size.
    text = text[:60000]

    system_prompt = """
You are StudyMate, an expert academic study assistant.

Turn the supplied study material into SHORT,
clear and high-quality revision notes.

Rules:

1. Use only information in the supplied material.
2. Do not invent facts.
3. Focus on concepts likely to be examined.
4. Use clear headings.
5. Use bullet points where useful.
6. Explain difficult concepts simply.
7. Include important definitions.
8. Include formulas only when they appear in the material.
9. Remove unnecessary repetition.
10. Make the notes easy to revise quickly.
11. Do not mention that you are an AI.
12. Do not create test questions.
"""

    user_prompt = f"""
Create concise revision notes from this study material.

STUDY MATERIAL:

{text}
"""

    notes, ai_error = ask_gemini(
        system_prompt,
        user_prompt,
        json_mode=False
    )

    if ai_error:
        return jsonify({
            "error": ai_error
        }), 500

    if not notes:
        return jsonify({
            "error":
                "The AI did not return any study notes."
        }), 500

    return jsonify({
        "message":
            "Study notes generated successfully.",
        "notes":
            notes
    }), 200


# ============================================================
# VALIDATE QUESTION
# ============================================================

def clean_test_question(question):
    if not isinstance(question, dict):
        return None

    question_text = str(
        question.get("question", "")
    ).strip()

    options = question.get("options")

    answer = question.get("answer")

    explanation = str(
        question.get("explanation", "")
    ).strip()

    if not question_text:
        return None

    if not isinstance(options, list):
        return None

    if len(options) != 4:
        return None

    cleaned_options = []

    for option in options:
        option = str(option).strip()

        if not option:
            return None

        cleaned_options.append(option)

    try:
        answer = int(answer)
    except (ValueError, TypeError):
        return None

    if answer < 0 or answer > 3:
        return None

    return {
        "question": question_text,
        "options": cleaned_options,
        "answer": answer,
        "explanation": explanation
    }


# ============================================================
# GENERATE ONE BATCH OF TEST QUESTIONS
# ============================================================

def generate_test_batch(
    text,
    previous_text,
    number_of_questions
):
    system_prompt = f"""
You are StudyMate's examination generator.

Generate EXACTLY {number_of_questions}
high-quality multiple-choice questions from the
supplied study material.

Return ONLY a valid JSON object.

Required structure:

{{
  "questions": [
    {{
      "question": "Question text",
      "options": [
        "Option A",
        "Option B",
        "Option C",
        "Option D"
      ],
      "answer": 0,
      "explanation": "Short explanation."
    }}
  ]
}}

Rules:

1. Generate exactly {number_of_questions} questions.
2. Every question has exactly 4 options.
3. Only one option is correct.
4. "answer" MUST be an integer from 0 to 3.
5. 0 means the first option.
6. 1 means the second option.
7. 2 means the third option.
8. 3 means the fourth option.
9. Use ONLY information in the supplied study material.
10. Do not invent facts.
11. Do not duplicate questions.
12. Mix easy, medium and difficult questions.
13. Test understanding, application and important facts.
14. Keep explanations concise.
15. Do not use markdown.
16. Return JSON only.
"""

    user_prompt = f"""
Generate {number_of_questions} questions.

STUDY MATERIAL:

{text}

{previous_text}
"""

    response, ai_error = ask_gemini(
        system_prompt,
        user_prompt,
        json_mode=True
    )

    if ai_error:
        return None, ai_error

    parsed = extract_json_from_ai_response(
        response
    )

    if not parsed:
        print(
            "Could not parse structured Gemini test response."
        )
        print(
            response[:5000]
        )

        return None, (
            "The AI returned an invalid test format. "
            "Please try again."
        )

    if isinstance(parsed, dict):
        questions = parsed.get(
            "questions",
            []
        )
    elif isinstance(parsed, list):
        questions = parsed
    else:
        questions = []

    if not isinstance(questions, list):
        return None, (
            "The AI did not return a valid question list."
        )

    valid_questions = []

    for item in questions:
        cleaned = clean_test_question(item)

        if cleaned:
            valid_questions.append(cleaned)

    return valid_questions, None


# ============================================================
# GENERATE 30 QUESTION AI TEST
# ============================================================

@app.route(
    "/api/generate-test",
    methods=["POST"]
)
def generate_test():
    user, error_response = get_current_user()

    if error_response:
        return error_response

    if gemini_client is None:
        return jsonify({
            "error":
                "Gemini is not configured on the server. "
                "Please add GEMINI_API_KEY to your environment variables."
        }), 500

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error":
                "No study material was provided."
        }), 400

    text = str(
        data.get("text", "")
    ).strip()

    if not text:
        return jsonify({
            "error":
                "Study material is empty."
        }), 400

    previous_questions = data.get(
        "previousQuestions",
        []
    )

    if not isinstance(previous_questions, list):
        previous_questions = []

    # Limit the material sent to Gemini.
    text = text[:60000]

    # --------------------------------------------------------
    # PREVIOUS QUESTIONS
    # --------------------------------------------------------

    cleaned_previous = []

    for question in previous_questions:
        if isinstance(question, str):
            question = question.strip()

            if question:
                cleaned_previous.append(question)

    previous_text = ""

    if cleaned_previous:
        previous_text = (
            "\n\n"
            "DO NOT REPEAT THESE PREVIOUS QUESTIONS:\n"
            + "\n".join(
                f"- {question}"
                for question in cleaned_previous[:50]
            )
        )

    # --------------------------------------------------------
    # FIRST ATTEMPT
    # --------------------------------------------------------

    print(
        "Starting AI test generation..."
    )

    questions, ai_error = generate_test_batch(
        text,
        previous_text,
        30
    )

    if ai_error:
        print(
            "First test generation attempt failed:",
            ai_error
        )

        return jsonify({
            "error": ai_error
        }), 500

    if not questions:
        return jsonify({
            "error":
                "The AI did not generate any valid questions. "
                "Please try again."
        }), 500

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    unique_questions = []
    seen_questions = set()

    for question in questions:
        normalized = re.sub(
            r"\s+",
            " ",
            question["question"]
            .strip()
            .lower()
        )

        if normalized in seen_questions:
            continue

        seen_questions.add(normalized)

        unique_questions.append(question)

    print(
        "First attempt produced",
        len(unique_questions),
        "unique valid questions."
    )

    # --------------------------------------------------------
    # RETRY IF GEMINI RETURNED FEWER THAN 30
    # --------------------------------------------------------

    if len(unique_questions) < 30:
        missing = 30 - len(unique_questions)

        print(
            "Generating",
            missing,
            "additional questions..."
        )

        existing_text = (
            "\n\nDO NOT REPEAT THESE QUESTIONS:\n"
            + "\n".join(
                f"- {q['question']}"
                for q in unique_questions
            )
        )

        retry_questions, retry_error = (
            generate_test_batch(
                text,
                existing_text + previous_text,
                missing
            )
        )

        if retry_error:
            print(
                "Retry failed:",
                retry_error
            )

        else:
            for question in retry_questions or []:
                normalized = re.sub(
                    r"\s+",
                    " ",
                    question["question"]
                    .strip()
                    .lower()
                )

                if normalized in seen_questions:
                    continue

                seen_questions.add(normalized)
                unique_questions.append(question)

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    if len(unique_questions) < 30:
        print(
            "Final question count:",
            len(unique_questions)
        )

        return jsonify({
            "error":
                (
                    "The AI could not generate all 30 valid "
                    "questions this time. It generated "
                    f"{len(unique_questions)} valid questions. "
                    "Please click Start test again."
                )
        }), 500

    unique_questions = unique_questions[:30]

    print(
        "SUCCESS: 30-question test generated."
    )

    return jsonify({
        "message":
            "30-question test generated successfully.",
        "questions":
            unique_questions
    }), 200

# ============================================================
# HANDLE LARGE UPLOADS
# ============================================================

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "error":
            (
                f"The uploaded file is too large. "
                f"Maximum PDF size is "
                f"{MAX_PDF_SIZE_MB} MB."
            )
    }), 413


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error":
            "The requested endpoint was not found.",
        "path":
            request.path
    }), 404


# ============================================================
# 405
# ============================================================

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error":
            "The requested method is not allowed."
    }), 405


# ============================================================
# 500
# ============================================================

@app.errorhandler(500)
def internal_server_error(error):
    print(
        "Unhandled server error:",
        repr(error)
    )

    return jsonify({
        "error":
            "An unexpected server error occurred."
    }), 500


# ============================================================
# INITIALIZE DATABASE TABLES
# ============================================================

try:
    initialize_pdf_storage()

except Exception as error:
    print(
        "Startup PDF storage initialization error:",
        repr(error)
    )


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )