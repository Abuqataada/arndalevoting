import mysql.connector
from mysql.connector import Error
import secrets
import string

def generate_voter_code():
    """Generate a unique 6-digit voter code"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))

def migrate_database():
    # MySQL connection configuration
    mysql_config = {
        'host': 'voting-db-abuqataada21-54f9.l.aivencloud.com',
        'port': 23198,
        'user': 'avnadmin',
        'password': 'AVNS_IttvoCuWeY-kq_jQebf',
        'database': 'defaultdb',
        'ssl_disabled': False
    }
    
    try:
        # Connect to MySQL
        print("Connecting to Aiven MySQL database...")
        connection = mysql.connector.connect(**mysql_config)
        
        if connection.is_connected():
            print("Successfully connected to MySQL database")
            
            cursor = connection.cursor()
            
            # Step 1: Add voter_code column to voters table
            print("Adding voter_code column to voters table...")
            try:
                cursor.execute("ALTER TABLE voters ADD COLUMN voter_code VARCHAR(10) UNIQUE")
                print("voter_code column added successfully")
            except Error as e:
                if "Duplicate column name" in str(e):
                    print("voter_code column already exists")
                else:
                    raise e
            
            # Step 2: Generate voter codes for existing voters
            print("Generating voter codes for existing voters...")
            
            # Get all voters without voter codes
            cursor.execute("SELECT id, name FROM voters WHERE voter_code IS NULL")
            voters_without_codes = cursor.fetchall()
            
            print(f"Found {len(voters_without_codes)} voters without voter codes")
            
            # Generate and assign unique voter codes
            for voter_id, voter_name in voters_without_codes:
                while True:
                    voter_code = generate_voter_code()
                    
                    # Check if code is unique
                    cursor.execute("SELECT id FROM voters WHERE voter_code = %s", (voter_code,))
                    if not cursor.fetchone():
                        break
                
                # Update voter with new code
                cursor.execute(
                    "UPDATE voters SET voter_code = %s WHERE id = %s",
                    (voter_code, voter_id)
                )
                print(f"Generated code {voter_code} for voter: {voter_name}")
            
            # Step 3: Make voter_code NOT NULL after populating all records
            print("Making voter_code column NOT NULL...")
            try:
                cursor.execute("ALTER TABLE voters MODIFY COLUMN voter_code VARCHAR(10) NOT NULL")
                print("voter_code column set to NOT NULL")
            except Error as e:
                print(f"ℹCould not set voter_code as NOT NULL: {e}")
            
            # Step 4: Verify the migration
            print("Verifying migration...")
            
            # Check total voters
            cursor.execute("SELECT COUNT(*) FROM voters")
            total_voters = cursor.fetchone()[0]
            print(f"Total voters in database: {total_voters}")
            
            # Check voters with codes
            cursor.execute("SELECT COUNT(*) FROM voters WHERE voter_code IS NOT NULL")
            voters_with_codes = cursor.fetchone()[0]
            print(f"Voters with voter codes: {voters_with_codes}")
            
            # Display sample of voters with their new codes
            cursor.execute("SELECT student_id, name, voter_code FROM voters LIMIT 10")
            sample_voters = cursor.fetchall()
            
            print("\nSample of voters with their new voter codes:")
            print("-" * 80)
            for student_id, name, voter_code in sample_voters:
                print(f"Student ID: {student_id}, Name: {name}, Voter Code: {voter_code}")
            print("-" * 80)
            
            # Commit changes
            connection.commit()
            print("\nDatabase migration completed successfully!")
            print(f"{voters_with_codes}/{total_voters} voters now have voter codes")
            
    except Error as e:
        print(f"Error during migration: {e}")
        if 'connection' in locals() and connection.is_connected():
            connection.rollback()
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("Database connection closed")

if __name__ == "__main__":
    migrate_database()