import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from scripts.seed_demo import seed
from src.config.database import Base, engine
from src.config.settings import SEED_DEMO
from src.domain.spec import SPEC
from src.middlewares import errors, headers, rate
from src.routes import distribution, identity, registry, runs
from src.utils.wakeup import broker

log = logging.getLogger(__name__)


def migrate(connection):
    """补建既有数据库缺失的列，与 002 号迁移说明保持一致。"""
    columns = {row[0] for row in connection.execute(text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'datasets'"))}
    if 'kind' not in columns:
        connection.execute(text("ALTER TABLE datasets ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'blockage'"))


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        migrate(connection)
    if SEED_DEMO:
        try:
            log.info('Seeded %s', seed())
        except Exception:
            log.exception('Demo seed failed')
    yield
    engine.dispose()


app = FastAPI(title=SPEC['title'], lifespan=lifespan)
errors.install(app)
headers.install(app)
rate.install(app)
for module in (identity, registry, runs):
    app.include_router(module.router)
if SPEC.get('scheduled'):
    app.include_router(distribution.router)


@app.get('/healthz', include_in_schema=False)
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    broker.ping()
    return {'status': 'ok'}
