import psycopg2
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def migrate_data():
    # Source: Aiven MySQL
    mysql_config = {
        'host': 'voting-db-abuqataada21-54f9.l.aivencloud.com',
        'port': 23198,
        'user': 'avnadmin',
        'password': 'AVNS_IttvoCuWeY-kq_jQebf',
        'database': 'defaultdb',
        'ssl': {'ssl': {}}
    }
    
    # Destination: Neon PostgreSQL
    postgres_url = os.environ.get('DATABASE_URL')
    
    try:
        print("Connecting to MySQL...")
        mysql_conn = pymysql.connect(**mysql_config)
        mysql_cursor = mysql_conn.cursor()
        
        print("Connecting to PostgreSQL...")
        postgres_conn = psycopg2.connect(postgres_url)
        postgres_cursor = postgres_conn.cursor()
        
        # Clear existing data in PostgreSQL (optional - remove if you want to keep existing data)
        print("Clearing existing PostgreSQL data...")
        tables = ['voting_log', 'candidates', 'voters', 'positions', 'sessions']
        for table in tables:
            try:
                postgres_cursor.execute(f"DELETE FROM {table}")
                print(f"Cleared {table}")
            except Exception as e:
                print(f"Note: Could not clear {table}: {e}")
        
        # Reset sequences (important for auto-increment IDs)
        sequences = ['sessions_id_seq', 'positions_id_seq', 'candidates_id_seq', 'voters_id_seq', 'voting_log_id_seq']
        for sequence in sequences:
            try:
                postgres_cursor.execute(f"ALTER SEQUENCE {sequence} RESTART WITH 1")
            except:
                pass  # Sequence might not exist yet
        
        # Migrate sessions (convert is_active from int to boolean)
        print("Migrating sessions...")
        mysql_cursor.execute("SELECT id, name, academic_year, is_active, created_date, description FROM sessions")
        sessions = mysql_cursor.fetchall()
        for session in sessions:
            session_id, name, academic_year, is_active_int, created_date, description = session
            is_active_bool = bool(is_active_int)  # Convert 1/0 to True/False
            postgres_cursor.execute(
                "INSERT INTO sessions (id, name, academic_year, is_active, created_date, description) VALUES (%s, %s, %s, %s, %s, %s)",
                (session_id, name, academic_year, is_active_bool, created_date, description)
            )
        print(f"Migrated {len(sessions)} sessions")
        
        # Migrate positions
        print("Migrating positions...")
        mysql_cursor.execute("SELECT id, name, session_id, display_order, description FROM positions")
        positions = mysql_cursor.fetchall()
        for position in positions:
            postgres_cursor.execute(
                "INSERT INTO positions (id, name, session_id, display_order, description) VALUES (%s, %s, %s, %s, %s)",
                position
            )
        print(f"Migrated {len(positions)} positions")
        
        # Migrate candidates
        print("Migrating candidates...")
        mysql_cursor.execute("SELECT id, name, position_id, photo_filename, grade, manifesto, votes FROM candidates")
        candidates = mysql_cursor.fetchall()
        for candidate in candidates:
            # Convert photo_filename to photo_url for Cloudinary
            candidate_id, name, position_id, photo_filename, grade, manifesto, votes = candidate
            photo_url = photo_filename  # Keep the same for now, will be Cloudinary URLs later
            postgres_cursor.execute(
                "INSERT INTO candidates (id, name, position_id, photo_url, grade, manifesto, votes) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (candidate_id, name, position_id, photo_url, grade, manifesto, votes)
            )
        print(f"Migrated {len(candidates)} candidates")
        
        # Migrate voters (convert has_voted from int to boolean)
        print("Migrating voters...")
        mysql_cursor.execute("SELECT id, student_id, name, grade, photo_filename, voter_code, registered_date, has_voted FROM voters")
        voters = mysql_cursor.fetchall()
        for voter in voters:
            voter_id, student_id, name, grade, photo_filename, voter_code, registered_date, has_voted_int = voter
            has_voted_bool = bool(has_voted_int)  # Convert 1/0 to True/False
            photo_url = photo_filename  # Convert to photo_url
            postgres_cursor.execute(
                "INSERT INTO voters (id, student_id, name, grade, photo_url, voter_code, registered_date, has_voted) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (voter_id, student_id, name, grade, photo_url, voter_code, registered_date, has_voted_bool)
            )
        print(f"Migrated {len(voters)} voters")
        
        # Migrate voting logs
        print("Migrating voting logs...")
        mysql_cursor.execute("SELECT id, session_id, position_id, candidate_id, voter_id, vote_timestamp FROM voting_log")
        logs = mysql_cursor.fetchall()
        for log in logs:
            postgres_cursor.execute(
                "INSERT INTO voting_log (id, session_id, position_id, candidate_id, voter_id, vote_timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
                log
            )
        print(f"Migrated {len(logs)} voting logs")
        
        postgres_conn.commit()
        print("\nMigration completed successfully!")
        print(f"Summary:")
        print(f"   Sessions: {len(sessions)}")
        print(f"   Positions: {len(positions)}")
        print(f"   Candidates: {len(candidates)}")
        print(f"   Voters: {len(voters)}")
        print(f"   Voting Logs: {len(logs)}")
        
    except Exception as e:
        print(f"Migration error: {e}")
        if 'postgres_conn' in locals():
            postgres_conn.rollback()
    finally:
        if 'mysql_conn' in locals():
            mysql_conn.close()
        if 'postgres_conn' in locals():
            postgres_conn.close()

if __name__ == '__main__':
    migrate_data()