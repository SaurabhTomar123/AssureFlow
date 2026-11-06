from src.db.session import engine, Base
import src.db.models


def init_db():
    Base.metadata.create_all(bind=engine)


def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables initialized successfully.")

