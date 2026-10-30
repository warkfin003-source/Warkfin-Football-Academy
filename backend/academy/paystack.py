"""Paystack hosted checkout with server pricing, signed events and independent verification."""
import hashlib
import hmac
import json
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import PaymentOrder
from . import payments

def ready():
    if settings.PAYSTACK_MODE == 'test' and not settings.DEBUG: return False
    prefix = 'sk_live_' if settings.PAYSTACK_MODE == 'live' else 'sk_test_'
    return bool(settings.PAYSTACK_ENABLED and settings.PAYSTACK_MODE in ('live','test') and settings.PAYSTACK_SECRET_KEY.startswith(prefix) and len(settings.PAYSTACK_SECRET_KEY) > len(prefix) + 10 and settings.PAYMENT_TERMS)

def is_order(order):
    return urlparse(order.checkout_url).hostname == 'checkout.paystack.com'

class ReferenceNotFound(payments.PaymentUnavailable):
    pass

def api(path, data=None):
    if not ready():
        raise payments.PaymentUnavailable('Paystack checkout is awaiting academy activation. No payment has been started.')
    try:
        request = Request('https://api.paystack.co' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + settings.PAYSTACK_SECRET_KEY, 'Content-Type': 'application/json', 'User-Agent': 'WarkfinAcademy/1.0', 'Accept': 'application/json'},
            method='POST' if data is not None else 'GET')
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(65536))
        if result.get('status') is not True or not isinstance(result.get('data'), dict):
            raise ValueError('Provider rejected request')
        return result['data']
    except HTTPError as exc:
        # Classify narrowly; never expose provider payloads or credentials.
        try:
            body = json.loads(exc.read(65536))
        except (ValueError, OSError):
            body = {}
        if not isinstance(body, dict): body = {}
        if (data is None and path.startswith('/transaction/verify/') and exc.code in (400,404)
            and body.get('status') is False
            and str(body.get('message','')).strip().rstrip('.').lower() == 'transaction reference not found'):
            raise ReferenceNotFound('Paystack has no transaction for this reference.') from exc
        if exc.code == 401:
            message = 'Paystack rejected the academy server key. The owner must check the live secret key in Render.'
        elif exc.code == 403:
            message = 'Paystack denied this request. The owner must check merchant activation and API access with Paystack.'
        elif exc.code == 429:
            message = 'Paystack is temporarily limiting requests. Wait before checking this same order again.'
        else:
            message = 'Paystack could not process this request. Keep this order reference and contact the academy.'
        raise payments.PaymentUnavailable(message) from exc
    except Exception as exc:
        raise payments.PaymentUnavailable('Paystack could not confirm this request. Check your existing order before trying another payment.') from exc

def initialize(order):
    result = api('/transaction/initialize', {'email': order.user.email, 'amount': order.amount_kobo,
        'currency': 'NGN', 'reference': order.reference.hex,
        'callback_url': settings.PORTAL_ORIGIN + '/payments/paystack/return/'})
    url = result.get('authorization_url', '')
    parsed = urlparse(url)
    if result.get('reference') != order.reference.hex or parsed.scheme != 'https' or parsed.hostname != 'checkout.paystack.com' or parsed.username or parsed.password or parsed.port not in (None,443):
        raise payments.PaymentUnavailable('Paystack checkout could not be verified. Contact the academy before paying.')
    PaymentOrder.objects.filter(pk=order.pk, status='pending').update(checkout_url=url)
    return url

def reconcile(order, allow_unstarted=False):
    if (not is_order(order) and not (allow_unstarted and not order.checkout_url)) or hasattr(order, 'transfer_claim'):
        raise payments.PaymentUnavailable('This order is not a Paystack checkout.')
    try:
        data = api('/transaction/verify/' + order.reference.hex)
    except ReferenceNotFound:
        if not allow_unstarted or order.checkout_url:
            raise
        from django.db import transaction
        from .models import AuditEvent
        with transaction.atomic():
            changed = PaymentOrder.objects.filter(pk=order.pk,status='pending',checkout_url='').update(status='closed')
            if changed:
                AuditEvent.objects.create(actor=None,action='payment.unstarted_reference_not_found',object_reference=f'paymentorder:{order.pk}')
        order.refresh_from_db()
        return order
    customer = data.get('customer')
    if not isinstance(customer, dict): raise ValueError('Missing customer identity')
    if (data.get('reference') != order.reference.hex or data.get('currency') != 'NGN'
        or type(data.get('amount')) is not int or data['amount'] != order.amount_kobo
        or data.get('domain') != settings.PAYSTACK_MODE
        or str(customer.get('email', '')).lower() != order.user.email.lower()):
        raise ValueError('Payment verification mismatch')
    if data.get('status') != 'success':
        return order  # Keep uncertain/abandoned results pending; never fabricate a paid receipt.
    if type(data.get('id')) is not int or data['id'] <= 0:
        raise ValueError('Missing transaction identity')
    return payments.settle(order, {'orderId': order.reference.hex, 'currency': 'NGN',
        'amount': data['amount'], 'orderNo': 'paystack:' + str(data['id']), 'orderStatus': 2})

@csrf_exempt
@require_POST
def notify(request):
    if not ready(): return HttpResponse('unavailable', status=503)
    if len(request.body) > 16384: return HttpResponse('invalid', status=400)
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), request.body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get('X-Paystack-Signature', '')):
        return HttpResponse('invalid', status=403)
    try:
        event = json.loads(request.body)
        if event.get('event') != 'charge.success': return HttpResponse('ignored')
        order = get_object_or_404(PaymentOrder, reference=event.get('data', {}).get('reference'))
        reconcile(order)
        return HttpResponse('ok')
    except payments.PaymentUnavailable: return HttpResponse('retry', status=503)
    except (ValueError, TypeError, AttributeError, ValidationError): return HttpResponse('unconfirmed', status=400)

@login_required
def returned(request):
    # The browser callback is informational; no GET request settles financial records.
    messages.info(request, 'Returned from checkout. Your receipt appears after server verification. Use Check payment status if confirmation is still pending; do not pay again.')
    return redirect('billing')
