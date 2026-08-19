from app.core.config import get_settings
from app.db.database import close_database, connect_database, create_tables, init_database


def main() -> None:
    init_database(get_settings())
    connect_database()
    create_tables()
    close_database()
    print("Database tables are ready.")


if __name__ == "__main__":
    main()
