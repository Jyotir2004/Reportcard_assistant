from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import ReportCard, Student


@transaction.atomic
def generate_report_cards():
    students = Student.objects.annotate(
        calculated_total=Coalesce(
            Sum(
                "subject_marks__marks",
                filter=Q(subject_marks__examination__isnull=True),
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    ).filter(
        Q(subject_marks__isnull=True)
        | Q(subject_marks__examination__isnull=True)
    ).distinct().order_by("-calculated_total", "pk")
    generated_at = timezone.now()
    existing_cards = {
        card.student_id: card
        for card in ReportCard.objects.select_for_update().filter(
            examination__isnull=True
        )
    }

    to_create = []
    to_update = []
    previous_total = None
    current_rank = 0

    for position, student in enumerate(students, start=1):
        total = student.calculated_total
        if total != previous_total:
            current_rank = position
            previous_total = total

        card = existing_cards.get(student.pk)
        if card is None:
            to_create.append(
                ReportCard(
                    student=student,
                    total_marks=total,
                    rank=current_rank,
                    generated_at=generated_at,
                )
            )
        else:
            card.total_marks = total
            card.rank = current_rank
            card.generated_at = generated_at
            to_update.append(card)

    ReportCard.objects.bulk_create(to_create, batch_size=500)
    ReportCard.objects.bulk_update(
        to_update,
        ["total_marks", "rank", "generated_at"],
        batch_size=500,
    )
    return len(to_create) + len(to_update)
