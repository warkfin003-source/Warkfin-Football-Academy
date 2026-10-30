"""Private payment statements; only verified collections count towards totals."""
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from .models import PaymentOrder
from .views import owner_required


def history(request, owner=False):
    orders = PaymentOrder.objects.select_related('user', 'user__application', 'transfer_claim', 'refund').prefetch_related('covered_months').order_by('-created_at', '-pk')
    if not owner:
        orders = orders.filter(user=request.user)
    status = request.GET.get('status', 'paid' if owner else 'all')
    if status not in ('all', 'paid', 'pending', 'failed', 'closed'): status = 'paid' if owner else 'all'
    purpose = request.GET.get('purpose', '')
    query = request.GET.get('q', '').strip()[:120] if owner else ''
    if status != 'all': orders = orders.filter(status=status)
    if purpose in ('dues', 'registration'): orders = orders.filter(purpose=purpose)
    else: purpose = ''
    if query:
        orders = orders.filter(Q(payer_name__icontains=query) | Q(user__email__icontains=query) | Q(user__application__phone__icontains=query) | Q(provider_reference__icontains=query))
    total = orders.filter(status='paid').aggregate(total=Sum('amount_kobo'))['total'] or 0
    printing = request.GET.get('print') == '1'
    page = Paginator(orders, 25).get_page(request.GET.get('page'))
    params = request.GET.copy(); params.pop('page', None); params.pop('print', None)
    return render(request, 'payment_history.html', {'owner_history': owner, 'orders': orders if printing else page,
        'page': page, 'printing': printing, 'status': status, 'purpose': purpose, 'query': query,
        'filters': params.urlencode(), 'record_count': orders.count(), 'verified_total': Decimal(total)/100,
        'generated_at': timezone.now()})


@login_required
def player_history(request):
    return history(request)


@owner_required
def owner_history(request):
    return history(request, owner=True)


@owner_required
def owner_receipt(request, pk):
    order = get_object_or_404(PaymentOrder.objects.select_related('user', 'user__application'), pk=pk, status='paid')
    return render(request, 'receipt.html', {'order': order, 'owner_receipt': True})
