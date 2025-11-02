import mysql.connector
from contextlib import asynccontextmanager
import database as db
from colorama import Fore

class DatabaseManager:

    @staticmethod
    @asynccontextmanager
    async def get_connection():
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=db.ip,
                user=db.user,
                port=3306,
                password=db.password,
                database=db.database,
                autocommit=False  # Contrôle manuel des transactions
            )
            cursor = connection.cursor()

            yield cursor, connection

        except mysql.connector.Error as e:
            if connection:
                connection.rollback()  # Annule la transaction en cas d'erreur
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    @staticmethod
    async def execute_query(query: str, params: tuple = None, fetch: bool = False, logger=None):
        print(Fore.BLUE + f"[QUERY] : {query}" + Fore.RESET)
        async with DatabaseManager.get_connection() as (cursor, connection):
            try:
                cursor.execute(query, params or ())
                if fetch:
                    return cursor.fetchall()
                else:
                    connection.commit()
                    return cursor.rowcount, cursor.lastrowid  # Nombre de lignes affectées
            except mysql.connector.errors.ProgrammingError or mysql.connector.errors.IntegrityError as e:
                if logger:
                    logger.log(f"[Database] SQL command: `{query}` params: ({params}) ERROR: {e}")
                else:
                    print(f"[Database] SQL command: `{query}` params: ({params}) ERROR: {e}")

    @staticmethod
    async def execute_many(query: str, params_list: list):

        async with DatabaseManager.get_connection() as (cursor, connection):
            cursor.executemany(query, params_list)
            connection.commit()
            return cursor.rowcount
