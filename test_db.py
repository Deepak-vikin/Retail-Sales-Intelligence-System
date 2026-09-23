from app.core.database import connection
try:
    conn=connection()
    print("SUCCESS")
    conn.close()
except Exception as e:
    print("FAILURE")
    print(e)
    
