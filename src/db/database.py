import sqlite3
import datetime
import threading
from passlib.context import CryptContext
from util.log_config import setup_logging

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

logger = setup_logging('db')

class DB:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Initiates new DB instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DB, cls).__new__(cls)
                    cls._instance.initialize()
        return cls._instance

    @classmethod
    def get_instance(cls):
        """Returns DB instance 
        """
        if cls._instance is None:
            cls._instance = DB()
        return cls._instance
    
    def initialize(self):
        """Creates app.db with a new thread
        """
        logger.info("Initializing DB class")
        self.local = threading.local()
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.db_file = 'app.db'
        self.create_db()

    def get_connection(self):
        """Returns db connection & cursor
        """
        if not hasattr(self.local, 'connection') or self.local.connection is None:
            self.local.connection = sqlite3.connect(self.db_file)
            self.local.connection.row_factory = sqlite3.Row
            self.local.cursor = self.local.connection.cursor()
        return self.local.connection, self.local.cursor

    def close_connection(self):
        """Closes connection with db
        """
        if hasattr(self.local, 'connection') and self.local.connection:
            self.local.connection.close()
            self.local.connection = None
            self.local.cursor = None

    def create_db(self):
        """Creates db schemas 
        """
        try:
            conn, cursor = self.get_connection()
            if not self._fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"):
                logger.info('Creating Database tables...')
                self._create_table('users', '''
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'tutor',
                    token TEXT,
                    expires_at TIMESTAMP
                ''')
                logger.info('Database created successfully.')
                self.register_user({"role": "admin", "username": "test", "password": "test"})
        except sqlite3.Error as e:
            logger.error(f"SQLite error in create_db: {e}", exc_info=True)
            raise
        finally:
            self.close_connection()

    def _execute_query(self, query, params=None):
        """Executes db query and commits it 
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

    def _fetch_one(self, query, params=None):
        """Fetches only one result from query 
        """
        cursor = self._execute_query(query, params)
        return cursor.fetchone()

    def _create_table(self, table_name: str, schema: str):
        """Creates table in db if it doesnt exist yet

        Args:
            table_name (str): table name 
            schema (str): sql table definition statement
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

    def get_user(self, username: str) -> dict:
        """Gets user config from username (username) 

        Args:
            username (str): user username 

        Returns:
            dict: user data 
        """
        try:
            user_data = self._fetch_one("SELECT * FROM users WHERE username = ?", (username,))
            return dict(user_data) if user_data else None
        except sqlite3.Error as e:
            logger.error(f"Error fetching user {username}: {e}")
            raise

    def register_user(self, user_data: dict):
        """Registrates a new user 

        Args:
            user_data (dict): user_id, username, pw_hash, role, (token), (expires_at)
        """
        logger.info(f"Attempting to register user with username: {user_data['username']}")
        try:
            try:
                password_hash = self.pwd_context.hash(user_data['password'])
            except Exception as e:
                logger.error(f"Error hashing password for user {user_data['username']}: {e}", exc_info=True)
                raise ValueError("Password hashing failed")
            role = user_data.get('role', 'tutor').lower()
            if role not in ['admin', 'tutor']:
                raise ValueError("Role must be 'admin' or 'tutor'")
            self._execute_query('''
                INSERT INTO users (
                    username, password_hash, role
                ) VALUES (?, ?, ?)
            ''', (user_data['username'], password_hash, role))
            logger.info(f"User registered successfully: {user_data['username']}")
        except sqlite3.IntegrityError:
            logger.warning(f"User registration failed, username already exists: {user_data['username']}")
            raise ValueError("Username already exists")
        except Exception as e:
            logger.error(f"Unexpected error in register_user: {str(e)}", exc_info=True)
            raise

    def get_refresh_token(self, token: str) -> dict:
        """Refreshes authentication token in db for user 

        Args:
            token (str): current user token

        Returns:
            dict: {username, expires} with expires being expiration date
        """
        logger.info(f"Retrieving refresh token: {token[:10]}...")
        try:
            result = self._fetch_one('SELECT username, expires_at FROM users WHERE token = ?', (token,))
            if result:
                expires_at = datetime.datetime.fromisoformat(result['expires_at']).replace(tzinfo=datetime.timezone.utc)
                return {
                    'username': result['username'],
                    'expires': expires_at
                }
            logger.warning(f"Refresh token not found: {token[:10]}...")
            return None
        except Exception as e:
            logger.error(f"Error retrieving refresh token: {e}")
            raise
        
    def get_user_role(self, username): 
        try: 
            role = self._fetch_one('SELECT ROLE FROM USERS WHERE USERNAME = ?', (username,))
            if role: 
                return role 
            logger.warning(f"Role for user not found {username}")
            return None 
        except Exception as e: 
            logger.error(f"Failed to retrieve user role: {e}")
            raise 

db = DB.get_instance()

