from django.db import migrations


def add_missing_result_columns(apps, schema_editor):
    """Ensure recently-added OptimizationResult fields exist in older databases."""

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
        # If the table is missing altogether we let Django handle it via the
        # normal migration chain (e.g. on a fresh database).
        return

    column_definitions = {
        "abay_net_actual_cfs": "REAL",
        "abay_net_expected_cfs": "REAL",
        "abay_net_expected_cfs_no_bias": "REAL",
        "abay_net_expected_cfs_with_bias": "REAL",
        "bias_cfs": "REAL",
        "expected_abay_af": "REAL",
        "expected_abay_ft": "REAL",
        "head_limit_mw": "REAL",
        "is_forecast": "INTEGER NOT NULL DEFAULT 0",
        "mfra_side_reduction_mw": "REAL",
        "regulated_component_cfs": "REAL",
    }

    for field_name, definition in column_definitions.items():
        if field_name in existing_columns:
            continue

        schema_editor.execute(
            "ALTER TABLE {table} ADD COLUMN {column} {definition}".format(
                table=schema_editor.quote_name(table_name),
                column=schema_editor.quote_name(field_name),
                definition=definition,
            )
        )
        existing_columns.add(field_name)


class Migration(migrations.Migration):

    dependencies = [
        ("optimization_api", "0011_optimizationresult_raw_values"),
    ]

    operations = [
        migrations.RunPython(add_missing_result_columns, migrations.RunPython.noop),
    ]