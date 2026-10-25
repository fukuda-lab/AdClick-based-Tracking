countries = ["JP", "DE", "AU", "US", "BR", "ZA"]
case_names = ["no-interaction", "accept-all", "reject-all"]
from libs.dbProcess import get_db_conn,update_cfg


import getpass
from psycopg2 import sql

def load_sql(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def create_tables(conn):
    query = load_sql("sql/create_tables.sql")
    with conn.cursor() as cur:
        cur.execute(query)
        conn.commit()

def create_db(conn, DB_NAME):
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(
            sql.Identifier(DB_NAME)
        ))
        #conn.commit()
    
    conn.autocommit = False


DB_HOST = input("Postgres host (localhost [default] / IP): ")
DB_PORT = input("Port [default 5432]: ")
DB_USER = input("Postgres username: ")
DB_PASSWORD = getpass.getpass("Postgres password: ")

DB_PREFIX_NAME = input("Database prefix name: ")



try:
    update_cfg(DB_HOST, DB_PORT, DB_PREFIX_NAME, DB_USER, DB_PASSWORD)

    for country in countries:
        for case_name in case_names:
            DB_NAME = f"{DB_PREFIX_NAME}_{country}_{case_name}"

            print(f"Creating structure for {DB_NAME} ...")
            try:
                with get_db_conn(country,case_name,default=True) as conn:
                   create_db(conn, DB_NAME)
                
                update_cfg(DB_HOST, DB_PORT, DB_PREFIX_NAME, DB_USER, DB_PASSWORD)

                try:
                    with get_db_conn(country, case_name) as conn:
                        create_tables(conn)
                except Exception as ex:
                    print("Error creating tables: ", ex)

                print("Done!")

            except Exception as ex:
                print("Error creating db: ", ex)
    
except Exception as e:
    print(e)
