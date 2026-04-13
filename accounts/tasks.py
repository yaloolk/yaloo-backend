# accounts/tasks.py

import logging
from datetime import date, timedelta

from celery import shared_task
from django.db.models import Q

logger = logging.getLogger(__name__)


@shared_task(
    name='accounts.tasks.cleanup_past_availability_slots',
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # retry after 60s if it fails
)
def cleanup_past_availability_slots(self):
    """
    Delete past unbooked guide availability slots.
    Scheduled to run daily at 2 AM (Asia/Colombo) via Celery Beat.
    """
    try:
        # Import here to avoid circular imports at module load time
        from accounts.models import GuideAvailability

        cutoff_date = date.today()

        slots_qs = GuideAvailability.objects.filter(
            Q(date__lt=cutoff_date) &
            Q(is_booked=False)
        )

        count = slots_qs.count()

        if count == 0:
            logger.info('✅ cleanup_past_availability_slots: nothing to delete')
            return {'deleted': 0}

        deleted_count, _ = slots_qs.delete()

        logger.info(
            f'✅ cleanup_past_availability_slots: deleted {deleted_count} '
            f'past unbooked slots (cutoff={cutoff_date})'
        )
        return {'deleted': deleted_count}

    except Exception as exc:
        logger.error(f'❌ cleanup_past_availability_slots failed: {exc}', exc_info=True)
        raise self.retry(exc=exc)