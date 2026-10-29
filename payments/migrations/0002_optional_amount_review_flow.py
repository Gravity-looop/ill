from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def backfill_submission_amounts(apps, schema_editor):
    Submission = apps.get_model("payments", "Submission")
    BalanceEntry = apps.get_model("payments", "BalanceEntry")
    submissions = Submission.objects.select_related("payment_request").all()

    for submission in submissions.iterator():
        if submission.status == "ACCEPTED":
            balance_entry = BalanceEntry.objects.filter(
                submission_id=submission.id
            ).first()
            if balance_entry is None:
                raise RuntimeError(
                    f"Accepted submission {submission.id} has no balance entry."
                )
            submission.proposed_amount = balance_entry.amount
            submission.final_amount = balance_entry.amount
        else:
            submission.proposed_amount = submission.payment_request.amount
        submission.save(update_fields=("proposed_amount", "final_amount"))


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentrequest",
            name="amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.01"))
                ],
            ),
        ),
        migrations.AddField(
            model_name="submission",
            name="proposed_amount",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.01"))
                ],
            ),
        ),
        migrations.AddField(
            model_name="submission",
            name="final_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.01"))
                ],
            ),
        ),
        migrations.RunPython(backfill_submission_amounts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="submission",
            name="proposed_amount",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=14,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.01"))
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("final_amount__isnull", True),
                    ("status__in", ["PENDING", "DECLINED"]),
                )
                | models.Q(
                    ("final_amount__isnull", False),
                    ("status", "ACCEPTED"),
                ),
                name="submission_final_amount_matches_status",
            ),
        ),
    ]
