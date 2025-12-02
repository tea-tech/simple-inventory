"""Script to create initial admin user."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.user import User, UserRole
from app.auth import get_password_hash


def create_admin():
    """Create initial admin user if not exists."""
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if admin exists
        admin = db.query(User).filter(User.role == UserRole.ADMINISTRATOR).first()
        if admin:
            print(f"Admin user already exists: {admin.username}")
            return
        
        # Create admin user
        admin_user = User(
            username="admin",
            email="admin@example.com",
            full_name="System Administrator",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMINISTRATOR,
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        print("Admin user created successfully!")
        print("Username: admin")
        print("Password: admin123")
        print("\nPlease change the password after first login!")
        
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
