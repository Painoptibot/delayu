"""#42 — human-in-the-loop для результатов ИИ."""
from django.utils import timezone

from delayu.models import AiHumanReview


def create_review(*, subsystem, user, title: str, ai_output: str, module_code: str = "M47"):
    return AiHumanReview.objects.create(
        subsystem=subsystem,
        user=user,
        module_code=module_code,
        title=title[:255],
        ai_output=ai_output,
        status=AiHumanReview.Status.PENDING,
    )


def approve_review(review: AiHumanReview, *, reviewer, comment: str = ""):
    review.status = AiHumanReview.Status.APPROVED
    review.reviewer = reviewer
    review.review_comment = comment
    review.reviewed_at = timezone.now()
    review.save(
        update_fields=["status", "reviewer", "review_comment", "reviewed_at"]
    )
    return review


def reject_review(review: AiHumanReview, *, reviewer, comment: str = ""):
    review.status = AiHumanReview.Status.REJECTED
    review.reviewer = reviewer
    review.review_comment = comment
    review.reviewed_at = timezone.now()
    review.save(
        update_fields=["status", "reviewer", "review_comment", "reviewed_at"]
    )
    return review
