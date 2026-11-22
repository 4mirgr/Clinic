from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('clinic', '0018_advice_revision')]
    operations = [
        migrations.AddField(model_name='appointment', name='calendar_review_required',
                            field=models.BooleanField(default=False)),
        migrations.AddField(model_name='appointment', name='calendar_checked_at',
                            field=models.DateTimeField(null=True, blank=True)),
    ]
