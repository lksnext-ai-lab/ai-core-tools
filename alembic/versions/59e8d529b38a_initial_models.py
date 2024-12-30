"""Initial models

Revision ID: 59e8d529b38a
Revises: df947a43f4ba
Create Date: 2024-12-29 20:50:06.219974

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '59e8d529b38a'
down_revision = 'df947a43f4ba'
branch_labels = None
depends_on = None


def upgrade():
    op.bulk_insert(
        sa.table('Model',
            sa.column('provider', sa.String),
            sa.column('name', sa.String),
            sa.column('description', sa.String)
        ),
        [
            {'provider': 'OpenAI', 'name': 'gpt-4o-mini', 'description': 'PT-4o mini (“o” for “omni”) is our most advanced model in the small models category, and our cheapest model yet. It is multimodal (accepting text or image inputs and outputting text), has higher intelligence than gpt-3.5-turbo but is just as fast. It is meant to be used for smaller tasks, including vision tasks.'},
            {'provider': 'OpenAI', 'name': 'gpt-4o', 'description': 'gpt-4o: Our high-intelligence flagship model for complex, multi-step tasks. gpt-4o is cheaper and faster than gpt-4 Turbo. Currently points to gpt-4o-2024-08-06.'}
        ]
    )


def downgrade():
    op.execute('DELETE FROM Model WHERE provider = "OpenAI"')
