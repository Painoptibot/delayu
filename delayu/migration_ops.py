"""Idempotent schema ops for production DBs that already have leftover invest columns."""

from django.db import migrations


def _table_names(schema_editor):
    return set(schema_editor.connection.introspection.table_names())


def _column_names(schema_editor, table):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return {col.name for col in description}


def _constraint_names(schema_editor, table):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, table).keys())


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        table = model._meta.db_table
        if table not in _table_names(schema_editor):
            super().database_forwards(app_label, schema_editor, from_state, to_state)
            return
        column = model._meta.get_field(self.name).column
        if column in _column_names(schema_editor, table):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class CreateModelIfMissing(migrations.CreateModel):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        if model._meta.db_table in _table_names(schema_editor):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddIndexIfMissing(migrations.AddIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        table = model._meta.db_table
        if table in _table_names(schema_editor) and self.index.name in _constraint_names(schema_editor, table):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
