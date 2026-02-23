from app.db.base import Base
from app.db.session import engine
import app.db.models  # noqa
import app.auth.models  # noqa
import app.rag.models  # noqa
import app.tenants.models  # noqa


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()