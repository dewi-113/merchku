import hashlib
import hmac
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class IntegrationError(Exception):
    pass


def _request_json(url, *, method='POST', headers=None, payload=None):
    # URL berasal dari konfigurasi; hanya izinkan https agar tidak bisa membaca file:// dsb.
    if not url.lower().startswith('https://'):
        raise IntegrationError('Alamat layanan eksternal harus memakai https.')
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=12) as response:  # nosec B310 - skema dibatasi https di atas
            return json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise IntegrationError('Layanan eksternal tidak dapat diproses saat ini.') from exc


def biteship_rates(config, user, cart_items):
    api_key = config.get('BITESHIP_API_KEY')
    origin_postal_code = config.get('SHIPPING_ORIGIN_POSTAL_CODE')
    if not api_key or not origin_postal_code:
        return []

    items = []
    for cart_item in cart_items:
        product = cart_item.product
        if product is None or not product.is_active:
            continue
        items.append({
            'name': product.name,
            'value': int(product.price),
            'weight': int(product.weight_gram or 500),
            'quantity': int(cart_item.quantity),
        })
    if not items:
        return []

    data = _request_json(
        f"{config['BITESHIP_BASE_URL'].rstrip('/')}/v1/rates/couriers",
        headers={
            'Authorization': api_key,
            'Content-Type': 'application/json',
        },
        payload={
            'origin_postal_code': origin_postal_code,
            'destination_postal_code': user.postal_code,
            'couriers': 'jne,jnt,sicepat,anteraja,pos',
            'items': items,
        },
    )
    pricing = data.get('pricing')
    if not isinstance(pricing, list):
        raise IntegrationError('Respons tarif Biteship tidak valid.')
    rates = []
    for rate in pricing:
        code = rate.get('courier_code')
        service_code = rate.get('courier_service_code')
        price = rate.get('price')
        if not code or not service_code or not isinstance(price, int) or price < 0:
            continue
        rates.append({
            'key': f'{code}|{service_code}',
            'courier': code,
            'service': rate.get('courier_service_name') or service_code,
            'price': price,
            'duration': rate.get('duration') or '',
        })
    return rates


def create_midtrans_payment(config, order, items, return_url):
    server_key = config.get('MIDTRANS_SERVER_KEY')
    if not server_key:
        raise IntegrationError('Midtrans belum dikonfigurasi.')
    import base64

    base_url = (
        'https://app.midtrans.com'
        if config.get('MIDTRANS_IS_PRODUCTION')
        else 'https://app.sandbox.midtrans.com'
    )
    transaction_id = f'MERCHKU-{order.id}-{uuid.uuid4().hex[:8]}'
    item_details = [
        {
            'id': str(item.product_id),
            'price': int(item.unit_price),
            'quantity': int(item.quantity),
            'name': item.product_name[:50],
        }
        for item in items
    ]
    shipping_total = max(0, int(order.shipping_cost) - int(order.shipping_discount or 0))
    if shipping_total:
        item_details.append({
            'id': 'shipping',
            'price': shipping_total,
            'quantity': 1,
            'name': f'Pengiriman {order.courier_label} {order.shipping_service or ""}'.strip()[:50],
        })
    for item_id, amount, item_name in (
        ('service-fee', order.service_fee, 'Biaya layanan'),
        ('fragile-protection', order.fragile_fee, 'Perlindungan kemasan'),
    ):
        if amount:
            item_details.append({
                'id': item_id,
                'price': int(amount),
                'quantity': 1,
                'name': item_name,
            })
    payload = {
        'transaction_details': {
            'order_id': transaction_id,
            'gross_amount': int(order.total_price),
        },
        'item_details': item_details,
        'customer_details': {
            'first_name': order.recipient_name[:50],
            'email': order.user.email,
            'phone': order.phone,
            'shipping_address': {
                'first_name': order.recipient_name[:50],
                'phone': order.phone,
                'address': order.address[:200],
                'city': order.city,
                'postal_code': order.postal_code,
                'country_code': 'IDN',
            },
        },
        'callbacks': {'finish': return_url},
    }
    authorization = base64.b64encode(f'{server_key}:'.encode()).decode()
    response = _request_json(
        f'{base_url}/snap/v1/transactions',
        headers={
            'Authorization': f'Basic {authorization}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        payload=payload,
    )
    token = response.get('token')
    redirect_url = response.get('redirect_url')
    if not token or not redirect_url:
        raise IntegrationError('Midtrans tidak memberikan tautan pembayaran.')
    return transaction_id, token, redirect_url


def verify_midtrans_notification(payload, server_key):
    order_id = str(payload.get('order_id', ''))
    status_code = str(payload.get('status_code', ''))
    gross_amount = str(payload.get('gross_amount', ''))
    signature = str(payload.get('signature_key', ''))
    if not all((order_id, status_code, gross_amount, signature, server_key)):
        return False
    expected = hashlib.sha512(
        f'{order_id}{status_code}{gross_amount}{server_key}'.encode()
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
