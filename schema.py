from app.core.database import connection
conn = connection()
cursor = conn.cursor()
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'suppliers';")
print(cursor.fetchall())
