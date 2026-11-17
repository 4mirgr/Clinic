from django.db import migrations


def populate(apps,schema_editor):
    from clinic.advice_text import search_document
    Advice=apps.get_model('clinic','Advice')
    for advice in Advice.objects.all().iterator():
        Advice.objects.filter(pk=advice.pk).update(search_text=search_document(advice))


class Migration(migrations.Migration):
    dependencies=[('clinic','0010_education_library_packets')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]
