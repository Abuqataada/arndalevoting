# update_database_fixed.py
import sys
import os
from datetime import datetime
from sqlalchemy import text

# Load environment variables FIRST
from dotenv import load_dotenv
load_dotenv()

# Add the current directory to the path so we can import from index.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Now import after loading environment variables
from index import db, app, Position, Session

def update_database():
    """Update the database with new fields for double voting system"""
    
    print("=" * 60)
    print("ARNDALE VOTING SYSTEM - DATABASE UPDATE SCRIPT")
    print("=" * 60)
    print("\nThis script will:")
    print("1. Check if 'voting_type' column exists in positions table")
    print("2. Add 'voting_type' column if it doesn't exist")
    print("3. Set default voting_type for existing positions to 'single'")
    print("\nWARNING: This will modify your database structure.")
    print("Make sure you have a backup before proceeding!")
    print("=" * 60)
    
    # Ask for confirmation
    response = input("\nDo you want to continue? (yes/no): ").strip().lower()
    if response != 'yes' and response != 'y':
        print("Database update cancelled.")
        return
    
    try:
        with app.app_context():
            print("\nChecking current database state...")
            
            # Get database connection info
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'Unknown')
            print(f"Database URI: {db_uri}")
            
            # Check existing tables
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            print(f"\nExisting tables: {', '.join(sorted(existing_tables))}")
            
            # Check if multi_voting_log table exists
            if 'multi_voting_log' in existing_tables:
                print("PASS: 'multi_voting_log' table already exists.")
            else:
                print("WARNING: 'multi_voting_log' table not found (but this is OK for now).")
            
            print("\nStarting database updates...")
            
            # 1. Check if voting_type column exists in positions table
            print("\n1. Checking 'voting_type' column in positions table...")
            
            # Get columns in positions table
            position_columns = [col['name'] for col in inspector.get_columns('positions')]
            
            if 'voting_type' in position_columns:
                print("   PASS: 'voting_type' column already exists in positions table.")
                
                # Show current voting_type values
                positions = Position.query.all()
                print(f"   Found {len(positions)} positions:")
                for pos in positions[:5]:  # Show first 5
                    voting_type = getattr(pos, 'voting_type', 'Not set')
                    print(f"      - {pos.name}: voting_type = '{voting_type}'")
                if len(positions) > 5:
                    print(f"      ... and {len(positions) - 5} more positions")
                    
                # Check if we need to set default values
                positions_without_voting_type = Position.query.filter(
                    (Position.voting_type.is_(None)) | (Position.voting_type == '')
                ).all()
                
                if positions_without_voting_type:
                    print(f"   {len(positions_without_voting_type)} positions need voting_type set to 'single'")
                    for pos in positions_without_voting_type:
                        pos.voting_type = 'single'
                    db.session.commit()
                    print("   Updated positions with voting_type='single'")
                else:
                    print("   All positions already have voting_type set.")
                    
                return True  # Already have the column, nothing more to do
            else:
                print("   FAIL: 'voting_type' column NOT found in positions table.")
                print("   Adding 'voting_type' column...")
                
                # Determine database type
                is_postgresql = 'postgresql' in db_uri.lower()
                is_sqlite = 'sqlite' in db_uri.lower()
                
                if is_postgresql:
                    print("   PostgreSQL database detected")
                    # For PostgreSQL
                    try:
                        db.session.execute(text(
                            "ALTER TABLE positions ADD COLUMN voting_type VARCHAR(20) DEFAULT 'single'"
                        ))
                        db.session.commit()
                        print("   PASS: 'voting_type' column added to positions table.")
                    except Exception as e:
                        print(f"   ERROR: Failed to add column: {e}")
                        # Try without DEFAULT first
                        try:
                            db.session.execute(text(
                                "ALTER TABLE positions ADD COLUMN voting_type VARCHAR(20)"
                            ))
                            db.session.commit()
                            print("   Column added without default, setting values...")
                            
                            # Update existing rows
                            db.session.execute(text(
                                "UPDATE positions SET voting_type = 'single' WHERE voting_type IS NULL"
                            ))
                            db.session.commit()
                            print("   PASS: 'voting_type' column added and values set.")
                        except Exception as e2:
                            print(f"   ERROR: Alternative method also failed: {e2}")
                            return False
                
                elif is_sqlite:
                    print("   SQLite database detected")
                    print("   WARNING: SQLite requires special handling for ALTER TABLE")
                    print("   Creating new table with voting_type column...")
                    
                    # Get all existing positions data
                    positions = Position.query.all()
                    position_data = []
                    for pos in positions:
                        position_data.append({
                            'id': pos.id,
                            'name': pos.name,
                            'session_id': pos.session_id,
                            'display_order': pos.display_order,
                            'description': pos.description,
                            'grade_filter': pos.grade_filter
                        })
                    
                    print(f"   Found {len(position_data)} positions to migrate")
                    
                    # Drop the old table (SQLite doesn't support dropping columns)
                    try:
                        db.session.execute(text('DROP TABLE positions'))
                        db.session.commit()
                        print("   Old positions table dropped.")
                    except Exception as e:
                        print(f"   ERROR: Could not drop table: {e}")
                        return False
                    
                    # Recreate the table by forcing SQLAlchemy to create it
                    # We need to update the Position model first
                    print("   Please make sure your Position model has voting_type field defined.")
                    print("   Then run: db.create_all() to recreate the table.")
                    
                    # Try to recreate table
                    try:
                        db.create_all()
                        print("   Positions table recreated.")
                    except Exception as e:
                        print(f"   ERROR: Could not recreate table: {e}")
                        return False
                    
                    # Re-add all positions with voting_type='single'
                    for data in position_data:
                        # Check if Position model has voting_type attribute
                        if hasattr(Position, 'voting_type'):
                            new_pos = Position(
                                id=data['id'],
                                name=data['name'],
                                session_id=data['session_id'],
                                display_order=data['display_order'],
                                description=data['description'],
                                grade_filter=data['grade_filter'],
                                voting_type='single'
                            )
                        else:
                            new_pos = Position(
                                id=data['id'],
                                name=data['name'],
                                session_id=data['session_id'],
                                display_order=data['display_order'],
                                description=data['description'],
                                grade_filter=data['grade_filter']
                            )
                        db.session.add(new_pos)
                    
                    try:
                        db.session.commit()
                        print(f"   PASS: {len(position_data)} positions restored with voting_type='single'")
                    except Exception as e:
                        print(f"   ERROR: Could not restore positions: {e}")
                        db.session.rollback()
                        return False
                
                else:
                    print(f"   WARNING: Unknown database type: {db_uri}")
                    print("   Trying generic SQL...")
                    try:
                        db.session.execute(text(
                            "ALTER TABLE positions ADD COLUMN voting_type VARCHAR(20)"
                        ))
                        db.session.commit()
                        
                        # Set default values
                        db.session.execute(text(
                            "UPDATE positions SET voting_type = 'single'"
                        ))
                        db.session.commit()
                        print("   PASS: 'voting_type' column added.")
                    except Exception as e:
                        print(f"   ERROR: Failed to add column: {e}")
                        return False
            
            # 2. Verify the update
            print("\n2. Verifying database update...")
            
            # Refresh inspector
            inspector = db.inspect(db.engine)
            final_position_columns = [col['name'] for col in inspector.get_columns('positions')]
            
            if 'voting_type' in final_position_columns:
                print("   PASS: 'voting_type' column successfully added to positions table.")
                
                # Show sample data
                sample_positions = Position.query.limit(3).all()
                print("   Sample positions voting_type values:")
                for pos in sample_positions:
                    voting_type = getattr(pos, 'voting_type', 'Not set')
                    print(f"      - {pos.name}: voting_type = '{voting_type}'")
            else:
                print("   FAIL: 'voting_type' column still missing in positions table.")
                return False
            
            # 3. Show summary
            print("\n" + "=" * 60)
            print("DATABASE UPDATE COMPLETE")
            print("=" * 60)
            
            # Count statistics
            total_positions = Position.query.count()
            if hasattr(Position, 'voting_type'):
                single_voting_positions = Position.query.filter_by(voting_type='single').count()
                double_voting_positions = Position.query.filter_by(voting_type='double').count()
            else:
                single_voting_positions = total_positions
                double_voting_positions = 0
            
            print(f"\nPOSITIONS SUMMARY:")
            print(f"   Total positions: {total_positions}")
            print(f"   Single voting positions: {single_voting_positions}")
            print(f"   Double voting positions: {double_voting_positions}")
            
            print(f"\nTABLES SUMMARY:")
            for table in sorted(inspector.get_table_names()):
                columns = [col['name'] for col in inspector.get_columns(table)]
                print(f"   {table}: {len(columns)} columns")
            
            print("\nSUCCESS: Database update completed!")
            print("\nIMPORTANT NEXT STEPS:")
            print("1. Make sure your Position model has 'voting_type' field defined")
            print("2. Update the position management form to include 'voting_type' field")
            print("3. Restart your Flask application")
            print("4. Test the double voting functionality")
            
            return True
            
    except Exception as e:
        print(f"\nERROR: Database update failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Try to rollback
        try:
            db.session.rollback()
            print("Rolled back any pending changes.")
        except:
            pass
        
        return False


def test_database_connection():
    """Test database connection before proceeding"""
    print("Testing database connection...")
    
    try:
        with app.app_context():
            # Try to connect to the database
            db.engine.connect()
            print("SUCCESS: Database connection successful")
            
            # Check if tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if not tables:
                print("WARNING: No tables found in database. Is this a new database?")
                return False
            
            # Check for required tables
            required_tables = ['sessions', 'positions', 'candidates', 'voters']
            missing_tables = [table for table in required_tables if table not in tables]
            
            if missing_tables:
                print(f"WARNING: Missing required tables: {missing_tables}")
                print("   Make sure your database is properly initialized.")
                return False
            
            print("SUCCESS: All required tables exist")
            return True
            
    except Exception as e:
        print(f"ERROR: Database connection failed: {str(e)}")
        return False


def check_position_model():
    """Check if Position model has voting_type field"""
    print("\nChecking Position model definition...")
    
    # Check if voting_type is defined in Position model
    if hasattr(Position, 'voting_type'):
        print("SUCCESS: Position model has 'voting_type' field defined.")
        return True
    else:
        print("WARNING: Position model does not have 'voting_type' field.")
        print("\nYou need to update your Position model in index.py:")
        print("""
class Position(db.Model):
    __tablename__ = 'positions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    grade_filter = db.Column(db.String(50), nullable=True)
    voting_type = db.Column(db.String(20), default='single')  # Add this line
    """)
        return False


def manual_sql_commands():
    """Generate manual SQL commands for database update"""
    print("\n" + "=" * 60)
    print("MANUAL SQL COMMANDS FOR DATABASE UPDATE")
    print("=" * 60)
    
    # Get database info
    with app.app_context():
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    
    if 'postgresql' in db_uri.lower():
        print("\nFor PostgreSQL:")
        print("""
-- Check if column exists
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'positions' AND column_name = 'voting_type';

-- If it doesn't exist, add it
ALTER TABLE positions ADD COLUMN voting_type VARCHAR(20) DEFAULT 'single';

-- Update existing rows (if needed)
UPDATE positions SET voting_type = 'single' WHERE voting_type IS NULL;
""")
    else:
        print("\nFor SQLite:")
        print("""
-- Check if column exists (run in sqlite3 CLI)
PRAGMA table_info(positions);

-- If it doesn't exist, you need to recreate the table:
-- 1. Backup your data first!
-- 2. Create new table
CREATE TABLE positions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    session_id INTEGER NOT NULL,
    display_order INTEGER DEFAULT 0,
    description TEXT,
    grade_filter VARCHAR(50),
    voting_type VARCHAR(20) DEFAULT 'single',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 3. Copy data
INSERT INTO positions_new (id, name, session_id, display_order, description, grade_filter, voting_type)
SELECT id, name, session_id, display_order, description, grade_filter, 'single'
FROM positions;

-- 4. Drop old table
DROP TABLE positions;

-- 5. Rename new table
ALTER TABLE positions_new RENAME TO positions;
""")


if __name__ == "__main__":
    print("ARNDALE VOTING SYSTEM - DATABASE MIGRATION TOOL")
    print("Version 2.0: Adding Double Voting Support")
    print("-" * 60)
    
    # First, check if Position model is updated
    if not check_position_model():
        print("\nYou must update your Position model in index.py first!")
        print("Please add 'voting_type' field to the Position class.")
        response = input("\nDo you want to see the manual SQL commands instead? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            manual_sql_commands()
        sys.exit(1)
    
    # Test database connection
    if not test_database_connection():
        print("\nCannot proceed without database connection.")
        print("Please check your database configuration in .env file.")
        sys.exit(1)
    
    # Show options
    print("\nOptions:")
    print("1. Run automatic database update")
    print("2. Show manual SQL commands")
    print("3. Exit")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == '1':
        success = update_database()
        
        if success:
            print("\nSUCCESS: Database update completed!")
            print("\nNext steps:")
            print("1. Update your position creation form to include 'voting_type' field")
            print("2. Restart your Flask application")
            print("3. Test the double voting functionality")
        else:
            print("\nFAIL: Database update failed.")
            print("\nYou can try the manual SQL commands instead.")
            retry = input("Show manual SQL commands? (yes/no): ").strip().lower()
            if retry in ['yes', 'y']:
                manual_sql_commands()
        
    elif choice == '2':
        manual_sql_commands()
    else:
        print("Exiting...")