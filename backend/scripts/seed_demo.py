import json
from sqlalchemy import func, select
from src.config.database import Session
from src.constants.enums import Role
from src.domain.demo import demo_connection_rows, demo_rows
from src.domain.spec import PROFILES, SPEC
from src.models.identity import User
from src.models.source import Dataset
from src.services.datasets import save
from src.utils.security import hash_password


def seed():
    with Session.begin() as db:
        for role in Role:
            if not db.get(User, role.value):
                db.add(User(username=role.value, role=role, password_hash=hash_password(f'{role.value}-demo-2611')))
        item, created = save(db, SPEC['default_dataset'], SPEC['sample_name'], demo_rows(), 'seed')
        connections = PROFILES['connections']
        extra, extra_created = save(db, connections['default_dataset'], connections['sample_name'],
                                    demo_connection_rows(), 'seed', kind='connections')
        return {'users': db.scalar(select(func.count()).select_from(User)),
                'datasets': db.scalar(select(func.count()).select_from(Dataset)),
                'seed_dataset_id': item.id, 'row_count': item.row_count, 'checksum': item.checksum,
                'created_dataset': created, 'connections_dataset_id': extra.id,
                'connections_rows': extra.row_count, 'created_connections_dataset': extra_created}


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False))
