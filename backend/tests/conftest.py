"""
Pytest configuration and shared fixtures.

This file contains shared fixtures and configuration for all tests.
"""

import pytest
import sys
import os
from pathlib import Path

# Add backend directory to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


# ==================== MARKERS ====================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring database"
    )
    config.addinivalue_line(
        "markers", "unit: Unit tests without external dependencies"
    )
    config.addinivalue_line(
        "markers", "export: Export/Import functionality tests"
    )


# ==================== DATABASE FIXTURES ====================


@pytest.fixture(scope="session")
def test_db_url():
    """Create test database and return its URL."""
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    
    # Connection parameters for default postgres database
    default_db = "postgres"
    host = os.getenv("DATABASE_HOST", "localhost")
    port = os.getenv("DATABASE_PORT", "5432")
    user = os.getenv("DATABASE_USER", "iacoretoolsdev")
    password = os.getenv("DATABASE_PASSWORD", "iacoretoolsdev")
    
    # Test database name
    test_db_name = "mattin_test_temp"
    
    # Connect to default database to create test database
    conn = psycopg2.connect(
        dbname=default_db,
        user=user,
        password=password,
        host=host,
        port=port
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Drop test database if it exists
    try:
        cursor.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    except:
        pass
    
    # Create test database
    cursor.execute(f"CREATE DATABASE {test_db_name}")
    cursor.close()
    conn.close()
    
    # Return test database URL
    test_url = f"postgresql://{user}:{password}@{host}:{port}/{test_db_name}"
    
    yield test_url
    
    # Cleanup: Drop test database after all tests
    conn = psycopg2.connect(
        dbname=default_db,
        user=user,
        password=password,
        host=host,
        port=port
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Terminate all connections to test database
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{test_db_name}'
        AND pid <> pg_backend_pid()
    """)
    
    # Drop test database
    try:
        cursor.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    except:
        pass
    
    cursor.close()
    conn.close()


@pytest.fixture(scope="session")
def engine(test_db_url):
    """Create database engine for tests."""
    from sqlalchemy import create_engine
    from db.database import Base
    
    engine = create_engine(test_db_url)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Drop all tables after tests
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a new database session for each test."""
    from sqlalchemy.orm import sessionmaker
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    # Rollback any uncommitted changes
    session.rollback()
    session.close()


# ==================== TEST DATA FIXTURES ====================


@pytest.fixture
def test_app_id():
    """Default test app ID."""
    return 1


@pytest.fixture
def test_user_id():
    """Default test user ID."""
    return 1


# ==================== MOCK FIXTURES ====================


@pytest.fixture
def mock_api_key():
    """Mock API key for testing."""
    return "sk-test-mock-api-key-for-testing"


# ==================== CLEANUP FIXTURES ====================


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Cleanup test export files after each test."""
    import glob
    
    yield
    
    # Cleanup any test export files
    for pattern in ["test_export_*.json", "*_modified.json"]:
        for file in glob.glob(pattern):
            try:
                os.remove(file)
            except:
                pass
