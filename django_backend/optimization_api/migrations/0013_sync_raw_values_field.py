from django.db import migrations, models


def ensure_raw_values_column(apps, schema_editor):
    """Add the raw_values column if it is missing from the database."""
    table_name = "optimization_api_optimizationresult"
    connection = schema_editor.connection

    try:
        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                connection.cursor(), table_name
            )
        }
    except Exception:
        # Table is missing; let the normal migration chain handle it.
        return

    if "raw_values" in existing_columns:
        return

    OptimizationResult = apps.get_model("optimization_api", "OptimizationResult")
    field = models.JSONField(blank=True, default=dict)
    field.set_attributes_from_name("raw_values")
    schema_editor.add_field(OptimizationResult, field)


def backfill_raw_values(apps, schema_editor):
    """Ensure existing rows have a default JSON payload."""
    table_name = schema_editor.quote_name("optimization_api_optimizationresult")
    column_name = schema_editor.quote_name("raw_values")
    schema_editor.execute(
        f"UPDATE {table_name} SET {column_name} = '{{}}' "
        f"WHERE {column_name} IS NULL OR {column_name} = ''"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("optimization_api", "0012_fix_missing_result_columns"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="optimizationresult",
                    name="raw_values",
                    field=models.JSONField(blank=True, default=dict),
                ),
            ],
            database_operations=[
                migrations.RunPython(ensure_raw_values_column, migrations.RunPython.noop),
                migrations.RunPython(backfill_raw_values, migrations.RunPython.noop),
            ],
        ),
    ]
