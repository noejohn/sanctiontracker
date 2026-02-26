from django.db import migrations


def _rename_and_add_sanction_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    table_name = "authentication_sanction"
    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

        def rename_column(old_name, new_name):
            if old_name in existing_columns and new_name not in existing_columns:
                cursor.execute(
                    f'ALTER TABLE {table_name} RENAME COLUMN "{old_name}" TO "{new_name}"'
                )
                existing_columns.remove(old_name)
                existing_columns.add(new_name)

        rename_column("violation", "violation_snapshot")
        rename_column("issued", "date_issued")
        rename_column("hours_required", "required_hours")

        if "department" not in existing_columns:
            cursor.execute(
                "ALTER TABLE authentication_sanction ADD COLUMN department varchar(120) NOT NULL DEFAULT ''"
            )
            cursor.execute(
                "ALTER TABLE authentication_sanction ALTER COLUMN department DROP DEFAULT"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0006_servicehoursubmission_proof"),
    ]

    operations = [
        migrations.RunPython(_rename_and_add_sanction_columns, reverse_code=migrations.RunPython.noop),
    ]
