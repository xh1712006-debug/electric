from celery import shared_task
from django.utils import timezone
from .models import Relay
from .api_mock import compare_and_log_relay_check

@shared_task
def process_relay_autocheck(relay_id):
    """
    Background task to check a single relay.
    """
    try:
        relay = Relay.objects.get(pk=relay_id)
        
        # Only check if it's enabled
        if not relay.auto_check_enabled or relay.is_paused_for_correction:
            return "DISABLED_OR_PAUSED"
            
        # Perform check
        log = compare_and_log_relay_check(relay)
        
        # Calculate next check schedule
        relay.last_checked_at = timezone.now()
        
        # If one-time exact (e), disable it after check
        if relay.check_interval_unit == 'e':
            relay.auto_check_enabled = False
            relay.next_check_at = None
        elif not relay.is_paused_for_correction:
            # Only schedule next if not paused by mismatch
            relay.next_check_at = relay.calculate_next_check(from_time=relay.last_checked_at)
            
        relay.save()
        
        # Clear dashboard cache
        from django.core.cache import cache
        cache.delete('autocheck_dashboard_stats')
        
        return log.status if log else "NO_SHEET"
    except Relay.DoesNotExist:
        return "NOT_FOUND"

@shared_task
def schedule_due_autochecks():
    """
    Periodic task (run every 1 minute via Celery Beat)
    Finds all relays that are due for a check and queues them.
    """
    now = timezone.now()
    due_relays = Relay.objects.filter(
        auto_check_enabled=True,
        is_paused_for_correction=False,
        next_check_at__lte=now
    )
    
    count = 0
    for relay in due_relays:
        process_relay_autocheck.delay(relay.id)
        count += 1
        
    return f"Queued {count} autochecks."
