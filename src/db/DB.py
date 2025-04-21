"""For the little ammount that needs to be stored this class does it
"""
import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import secrets
import datetime
from ..util.log_config import setup_logging
import threading


logger = setup_logging('db')

class DB:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """
        Ensures only one instance of DB is created (Singleton pattern).
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DB, cls).__new__(cls)
                    cls._instance.initialize()
        return cls._instance

    @classmethod
    def get_instance(cls):
        """
        Returns the singleton instance of the DB class.
        """
        if cls._instance is None:
            cls._instance = DB()
        return cls._instance
    
    def initialize(self):
        """
        Initializes the DB instance with necessary attributes and creates the database.
        """
        logger.info("Initializing DB class")
        self.local = threading.local()
        self.ph = PasswordHasher()
        self.db_file = 'app.db'
        self.create_db()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()
        
    def get_connection(self):
        """
        Establishes and returns a database connection and cursor.
        """
        if not hasattr(self.local, 'connection') or self.local.connection is None:
            self.local.connection = sqlite3.connect(self.db_file)
            self.local.connection.row_factory = sqlite3.Row
            self.local.cursor = self.local.connection.cursor()
        return self.local.connection, self.local.cursor

    def close_connection(self):
        """
        Closes the database connection if it exists.
        """
        if hasattr(self.local, 'connection') and self.local.connection:
            self.local.connection.close()
            self.local.connection = None
            self.local.cursor = None

    def create_db(self):
        try:
            conn, cursor = self.get_connection()

            if not self._fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"):
                logger.info('Creating Database tables...')
                
                self._create_table('users', '''
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'TUTOR',
                    TOKEN TEXT,
                    expires_at TIMESTAMP
                ''') 
                
                
                logger.info('Database created successfully.')
                
                self._execute_query('INSERT OR IGNORE INTO settings (key, value) VALUES ("mahn_locked", 0)')
                
        except sqlite3.Error as e:
            logger.error(f"SQLite error in create_db: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error in create_db: {e}", exc_info=True)
            raise
        finally:
            self.close_connection()

    def _execute_query(self, query, params=None):
        """
        Executes an SQL query with optional parameters.
        """
        conn, cursor = self.get_connection()
        try:
            if params:
                if isinstance(params, list) and len(params) > 1:
                    cursor.executemany(query, params)
                else:
                    cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            logger.error(f"SQLite error executing query: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}", exc_info=True)
            raise

    def _fetch_one(self, query, params=None):
        """
        Executes a query and returns the first row of the result.
        """
        cursor = self._execute_query(query, params)
        return cursor.fetchone()

    def _fetch_all(self, query, params=None):
        """
        Executes a query and returns all rows of the result.
        """
        cursor = self._execute_query(query, params)
        return cursor.fetchall()

    def _create_table(self, table_name: str, schema: str):
        """
        Creates a table with the given name and schema if it doesn't exist.
        """
        try:
            self._execute_query(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                {schema}
            )
            ''')
            logger.debug(f"{table_name} table created")
        except sqlite3.Error as e:
            logger.error(f"Error creating {table_name} table: {e}", exc_info=True)
            raise


   
   
    def register_user(self, user_data: dict):
        logger.info(f"Attempting to register user with email: {user_data['email']}")
        try:
            password_hash = self.ph.hash(user_data['password'])
            role = user_data.get('role', 'worker') 
            logger.info('Creating registration token for user..')
            self._execute_query('''
                INSERT INTO users (
                    email, password_hash, role
                ) VALUES (?, ?, ?)
            ''', ( user_data['email'], password_hash, role))

            logger.info(f"User registered successfully: {user_data['email']}")

        except sqlite3.IntegrityError as e:
            logger.warning(f"User registration failed, email already exists: {user_data['email']}")
            raise ValueError("Email already exists")
        except Exception as e:
            logger.error(f"Unexpected error in register_user: {str(e)}", exc_info=True)
            raise


    def store_token(self, user_id, token, expiration_days=30):
        """
        Stores or updates an authentication token for a user.
        """
        logger.info(f"Storing token for user_id: {user_id}")
        try:
            expires_at = (datetime.datetime.now(datetime.timezone.utc) + 
                        datetime.timedelta(days=expiration_days))
            
            # Store the expires_at as an ISO format string with timezone info
            expires_at_str = expires_at.isoformat()
            
            # Check if a token already exists for this user
            existing_token = self._fetch_one('SELECT token FROM users WHERE user_id = ?', (user_id,))
            
            if existing_token:
                # Update the existing token
                self._execute_query('''
                    UPDATE users 
                    SET token = ?, expires_at = ? 
                    WHERE user_id = ?
                ''', (token, expires_at_str, user_id))
                logger.info(f"Token updated for user_id: {user_id}")
            else:
                # Insert a new token
                self._execute_query('''
                    UPDATE users 
                    SET token = ?, expires_at = ? 
                    WHERE user_id = ?
                ''', (token, expires_at_str, user_id))
                logger.info(f"New token stored for user_id: {user_id}")
            
            return True
        except Exception as e:
            logger.error(f"Error storing token for user_id {user_id}: {e}")
            return False

    def verify_token(self, token):
        """
        Verifies if a given token is valid and not expired.
        """
        logger.info(f"Verifying token: {token[:10]}...")  # Log only first 10 chars for security
        try:
            result = self._fetch_one('SELECT user_id, expires_at FROM auth_tokens WHERE token = ?', (token,))
            if result:
                user_id, expires_at_str = result
                current_time = datetime.datetime.now(datetime.timezone.utc)
                # Convert the stored expires_at string to an offset-aware datetime
                expires_at = datetime.datetime.fromisoformat(expires_at_str).replace(tzinfo=datetime.timezone.utc)
                
                logger.debug(f"Current time (UTC): {current_time}")
                logger.debug(f"Token expiration time (UTC): {expires_at}")
                
                if current_time < expires_at:
                    logger.info(f"Token verified successfully for user_id: {user_id}")
                    return True, user_id
                else:
                    logger.warning(f"Token expired for user_id: {user_id}")
            else:
                logger.warning("Token not found")
            return False, None
        except Exception as e:
            logger.error(f"Error verifying token: {e}", exc_info=True)
            return False, None

    def get_user_id_by_token(self, token):
        """
        Retrieves the user ID associated with a given token.
        """
        logger.info(f"Getting user_id for token: {token[:10]}...")  # Log only first 10 chars for security
        try:
            result = self._fetch_one('SELECT user_id FROM auth_tokens WHERE token = ?', (token,))
            if result:
                logger.info(f"User_id found for token: {token[:10]}...")
                return result[0]
            else:
                logger.warning(f"No user_id found for token: {token[:10]}...")
                return None
        except Exception as e:
            logger.error(f"Error getting user_id for token {token[:10]}...: {e}", exc_info=True)
            return None

    def authenticate_user(self, email, password):
        """
        Verifies user credentials and updates last login time if successful.
        """
        logger.info(f"Attempting to verify user: {email}")
        try:
            result = self._fetch_one('SELECT user_id, password_hash FROM users WHERE email = ?', (email,))
           
            if result:
                user_id, stored_hash = result
                try:
                    self.ph.verify(stored_hash, password)
                    logger.info(f"User verified successfully: {email}")
                    return True, user_id
                except VerifyMismatchError:
                    logger.warning(f"Password verification failed for user: {email}")
                    return False, user_id 
            else:
                logger.warning(f"User not found: {email}")
                return False, None 
        except Exception as e:
            logger.error(f"Unexpected error in verify_user: {e}", exc_info=True)
            return False, None 

    def get_user(self, username: str)-> tuple: 
        """Gets user data by username 

        Args:
            username (str): username

        Returns:
            tuple: user row in users table 
        """
        try: 
            user_data = self._execute_query("SELECT * FROM USERS WHERE EMAIL = ?", (username,))
            return user_data 
        except sqlite3.Error as e: 
            return e 

            
db = DB.get_instance()

if __name__ == '__main__':
    logger.info("Running db.py as main")
    db = DB()
    db.register_user({"email": "ranelkin23@gmail.com", "password": "test", "role": "worker"})