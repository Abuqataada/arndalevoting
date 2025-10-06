import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def fix_sequences():
    postgres_url = os.environ.get('DATABASE_URL')
    conn = psycopg2.connect(postgres_url)
    cursor = conn.cursor()
    
    try:
        print("Fixing PostgreSQL sequences...")
        
        # Fix voters sequence
        cursor.execute("SELECT MAX(id) FROM voters")
        max_voter_id = cursor.fetchone()[0] or 0
        
        cursor.execute(f"ALTER SEQUENCE voters_id_seq RESTART WITH {max_voter_id + 1}")
        print(f"Voters sequence reset to: {max_voter_id + 1}")
        
        # Fix other sequences
        tables = ['sessions', 'positions', 'candidates', 'voting_log']
        for table in tables:
            cursor.execute(f"SELECT MAX(id) FROM {table}")
            max_id = cursor.fetchone()[0] or 0
            cursor.execute(f"ALTER SEQUENCE {table}_id_seq RESTART WITH {max_id + 1}")
            print(f"{table} sequence reset to: {max_id + 1}")
        
        conn.commit()
        print("All sequences fixed successfully!")

    except Exception as e:
        print(f"Error fixing sequences: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    fix_sequences()