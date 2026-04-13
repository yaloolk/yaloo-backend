# accounts/management/commands/cleanup_past_availability.py
"""
Django management command to delete past unbooked availability slots.

Usage:
    python manage.py cleanup_past_availability

This should be run daily via cron or Celery Beat.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from datetime import date, timedelta
import logging

from accounts.models import GuideAvailability

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete past availability slots that are not booked'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-before',
            type=int,
            default=0,
            help='Delete slots older than N days (default: 0 = today)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        days_before = options['days_before']
        dry_run = options['dry_run']
        
        # Calculate cutoff date
        cutoff_date = date.today() - timedelta(days=days_before)
        
        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}Cleaning up availability slots before {cutoff_date}"
        )
        
        # Find slots to delete
        slots_to_delete = GuideAvailability.objects.filter(
            Q(date__lt=cutoff_date) &  # Past dates
            Q(is_booked=False)          # Not booked
        )
        
        count = slots_to_delete.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No slots to clean up'))
            return
        
        # Show details
        self.stdout.write(f"Found {count} slots to delete:")
        
        # Group by guide for reporting
        guides_affected = slots_to_delete.values('guide_profile_id').distinct().count()
        self.stdout.write(f"  - Affecting {guides_affected} guides")
        
        # Sample of slots being deleted
        sample = slots_to_delete[:10]
        for slot in sample:
            self.stdout.write(
                f"  - {slot.date} {slot.start_time}-{slot.end_time} "
                f"(Guide: {slot.guide_profile_id})"
            )
        
        if count > 10:
            self.stdout.write(f"  ... and {count - 10} more")
        
        # Delete unless dry run
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  DRY RUN - No slots were actually deleted'
                )
            )
        else:
            deleted_count, _ = slots_to_delete.delete()
            logger.info(
                f"Deleted {deleted_count} past unbooked availability slots before {cutoff_date}"
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Successfully deleted {deleted_count} slots'
                )
            )