from django.shortcuts import render

from apps.accounts.decorators import owner_required

from .models import AuditLog, SecurityEvent
import csv
from django.http import HttpResponse
from django.utils import timezone


@owner_required
def export_events_csv(request):
    """Owner-only CSV export of recent security events. Omits any sensitive data."""
    qs = SecurityEvent.objects.select_related('user').order_by('-created_at')[:1000]
    filename = f"security-events-{timezone.now().strftime('%Y%m%d-%H%M%S')}.csv"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        'created_at',
        'action',
        'result',
        'user',
        'target_type',
        'target_id',
        'ip_address',
        'request_id',
    ])
    for e in qs:
        user_repr = e.user.email if getattr(e.user, 'email', None) else (getattr(e.user, 'username', None) or '')
        writer.writerow([
            e.created_at.isoformat(),
            e.action,
            e.result,
            user_repr,
            e.target_type,
            e.target_id,
            e.ip_address or '',
            str(e.request_id),
        ])
    return response


@owner_required
def index(request):
    events = SecurityEvent.objects.select_related('user')[:200]
    request_logs = AuditLog.objects.select_related('user')[:100]
    return render(
        request,
        'audittrail/index.html',
        {'events': events, 'request_logs': request_logs},
    )
