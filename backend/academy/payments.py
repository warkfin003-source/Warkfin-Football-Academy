"""PalmPay collections: server pricing, authenticated callbacks and immutable receipts.

Integration reference: docs-daily.palmpay.com/en/pay-ins-palmpay-checkout-create-order.html.
Enable only after testing with the academy's approved merchant credentials.
"""
import base64
import hashlib
import json
import secrets
import time
from datetime import date, timedelta
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import PaymentOrder, DuesMonth, User, AuditEvent

REGISTRATION_KOBO = 500000
MONTH_KOBO = 300000
MONTH_OPTIONS = (1, 3, 6, 9, 12)

class PaymentUnavailable(Exception):
    """Safe public error; never include credentials or raw provider payloads."""


def ready():
    if not settings.DEBUG and settings.PALMPAY_BASE_URL.rstrip('/') != 'https://open-gw-prod.palmpay-inc.com': return False
    return bool(settings.PALMPAY_ENABLED and settings.PALMPAY_APP_ID and
                settings.PALMPAY_PRIVATE_KEY and settings.PALMPAY_PUBLIC_KEY and
                settings.PAYMENT_TERMS and any(settings.PALMPAY_CHECKOUT_HOSTS))


def month_sequence(start, count):
    """Calendar arithmetic, including December-to-January boundaries."""
    return [date(start.year + (start.month - 1 + n)//12,
                 (start.month - 1 + n)%12 + 1, 1) for n in range(count)]


def registration_paid(user):
    return PaymentOrder.objects.filter(user=user, purpose='registration', status='paid', amount_kobo=REGISTRATION_KOBO).exists()


def signature_payload(data):
    # PalmPay requires uppercase MD5 of ASCII-sorted, nonempty key/value pairs.
    values = []
    for key, value in sorted(data.items()):
        if key == 'sign' or value is None or value == '': continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(',', ':'), ensure_ascii=False)
        elif isinstance(value, bool): value = str(value).lower()
        values.append(f'{key}={str(value).strip()}')
    return hashlib.md5('&'.join(values).encode()).hexdigest().upper().encode()


def load_key(value, private=False):
    from cryptography.hazmat.primitives import serialization
    raw = value.replace('\\n', '\n').encode()
    if b'-----BEGIN' in raw:
        return serialization.load_pem_private_key(raw, password=None) if private else serialization.load_pem_public_key(raw)
    raw = base64.b64decode(raw)
    return serialization.load_der_private_key(raw, password=None) if private else serialization.load_der_public_key(raw)


def verify_signature(data):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    try:
        signature = base64.b64decode(unquote(data['sign']), validate=True)
        load_key(settings.PALMPAY_PUBLIC_KEY).verify(signature, signature_payload(data), padding.PKCS1v15(), hashes.SHA1())
        return True
    except (ValueError, TypeError, KeyError): return False
    except Exception: return False


def provider_request(path, data):
    """TLS-only signed requests; secrets and response bodies are never logged."""
    if not ready(): raise PaymentUnavailable('Online payment is awaiting activation. Please do not transfer money yet.')
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    base = settings.PALMPAY_BASE_URL.rstrip('/')
    if base not in ('https://open-gw-sandbox.palmpay-inc.com','https://open-gw-prod.palmpay-inc.com'):
        raise PaymentUnavailable('Payment configuration needs attention.')
    body = dict(data, requestTime=int(time.time()*1000), nonceStr=secrets.token_hex(16), version='V1.1')
    try:
        signed = load_key(settings.PALMPAY_PRIVATE_KEY, True).sign(signature_payload(body), padding.PKCS1v15(), hashes.SHA1())
        headers = {'Content-Type':'application/json', 'CountryCode':'NG',
                   'Authorization':'Bearer '+settings.PALMPAY_APP_ID,
                   'Signature':base64.b64encode(signed).decode()}
        req = Request(base+path, data=json.dumps(body).encode(), headers=headers, method='POST')
        with urlopen(req, timeout=20) as response:
            result = json.loads(response.read(65536))
        if result.get('respCode') != '00000000' or not isinstance(result.get('data'), dict):
            raise ValueError('Provider rejected request')
        return result['data']
    except Exception as exc:
        raise PaymentUnavailable('Payment provider unavailable. Check this order before trying another payment.') from exc


def make_order(user, purpose, start=None, months=0):
    """Serialize per-user checkout creation and reuse pending orders after retries."""
    if purpose not in ('registration','dues'): raise ValueError('Choose a valid payment type.')
    if purpose=='dues' and (months not in MONTH_OPTIONS or not start or start.day!=1):
        raise ValueError('Choose a valid starting month and payment period.')
    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)
        pending = PaymentOrder.objects.filter(user=user, status='pending').first()
        if pending: return pending
        if purpose=='registration' and registration_paid(user): raise ValueError('Registration is already paid.')
        if purpose=='dues' and DuesMonth.objects.filter(user=user, month__in=month_sequence(start, months)).exists():
            raise ValueError('One or more selected months are already paid. Choose unpaid months.')
        return PaymentOrder.objects.create(user=user, purpose=purpose, start_month=start if purpose=='dues' else None,
            months=months if purpose=='dues' else 0, amount_kobo=REGISTRATION_KOBO if purpose=='registration' else MONTH_KOBO*months,
            payer_name=getattr(getattr(user,'application',None),'full_name','') or user.get_full_name() or user.email)


def start_checkout(order):
    if order.checkout_url: return order.checkout_url
    result = provider_request('/api/v2/payment/merchant/createorder', {
        'orderId':order.reference.hex, 'amount':order.amount_kobo, 'currency':'NGN',
        'title':'Warkfin Academy '+order.get_purpose_display(),
        'notifyUrl':settings.PORTAL_ORIGIN+'/payments/palmpay/notify/',
        'callBackUrl':settings.PORTAL_ORIGIN+'/payments/', 'orderExpireTime':1800})
    url = result.get('checkoutUrl','')
    parsed = urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in settings.PALMPAY_CHECKOUT_HOSTS or parsed.username or parsed.password:
        raise PaymentUnavailable('The checkout address could not be verified. Contact the academy.')
    PaymentOrder.objects.filter(pk=order.pk, status='pending').update(checkout_url=url)
    return url


def settle(order, data):
    """Called only after a provider-signed callback AND server-to-server requery."""
    with transaction.atomic():
        User.objects.select_for_update().get(pk=order.user_id)
        order = PaymentOrder.objects.select_for_update().get(pk=order.pk)
        if (str(data.get('orderId')) != order.reference.hex or data.get('currency') != 'NGN'
            or type(data.get('amount')) is not int or data['amount'] != order.amount_kobo
            or not data.get('orderNo')):
            raise ValueError('Payment verification mismatch')
        if order.status=='paid':
            if order.provider_reference != data['orderNo']: raise ValueError('Provider reference mismatch')
            return order
        state = data.get('orderStatus')
        if state == 2:
            if order.purpose=='registration' and registration_paid(order.user): raise ValueError('Duplicate registration payment')
            if order.purpose=='dues':
                months=month_sequence(order.start_month, order.months)
                if DuesMonth.objects.filter(user=order.user,month__in=months).exists(): raise ValueError('Duplicate dues coverage')
                DuesMonth.objects.bulk_create([DuesMonth(user=order.user,month=m,payment=order) for m in months])
            order.status='paid'; order.paid_at=timezone.now(); order.provider_reference=data['orderNo']
            AuditEvent.objects.create(action='payment.verified',object_reference=f'paymentorder:{order.pk}')
        elif state in (3,4): order.status='failed' if state==3 else 'closed'
        order.save()
        return order


def reconcile(order):
    data = provider_request('/api/v2/payment/merchant/order/queryStatus', {'orderId':order.reference.hex})
    return settle(order, data)
