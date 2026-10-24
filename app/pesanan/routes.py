import contextlib
import os

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from app import csrf, db, limiter
from app.core.uploads import (
    MAX_PAYMENT_BYTES,
    UploadRejected,
    reencode_and_save,
    save_bytes,
    validate_image_upload,
)
from app.core.utils import get_client_ip, log_access_denied
from app.katalog.models import Product, ProductSizeStock
from app.keranjang.models import CartItem
from app.pesanan.forms import BuktiBayarForm, CheckoutForm
from app.pesanan.integrations import (
    IntegrationError,
    biteship_rates,
    create_midtrans_payment,
    verify_midtrans_notification,
)
from app.pesanan.models import (
    BUKTI_UPLOAD_ALLOWED,
    CUSTOMER_CANCELLABLE,
    Order,
    OrderItem,
    restore_reserved_stock,
)
from app.security_logger import sec_log

bp = Blueprint('pesanan', __name__, url_prefix='/pesanan')


def _log(event, **kw):
    """Helper log dengan konteks request/user.

    Nilai default hanya dipakai bila pemanggil tidak menyediakannya sendiri,
    sehingga pemanggil boleh meng-override (mis. `user_id`) tanpa error.
    """
    level = kw.pop('level', None)  # None: sec_log memilih info/warning sesuai event
    kw.setdefault('ip', get_client_ip(current_app.config.get('TRUSTED_PROXIES')))
    kw.setdefault('path', request.path)
    kw.setdefault('method', request.method)
    kw.setdefault('user_id', getattr(current_user, 'id', None))
    kw.setdefault('email', getattr(current_user, 'email', None))
    kw.setdefault('role', getattr(current_user, 'role', None))
    sec_log(event=event, level=level, **kw)



# ---------- routes ----------

@bp.route('/checkout', methods=['GET', 'POST'])
@login_required
@limiter.limit(
    '10 per hour',
    key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr,
)
def checkout():
    """
    Tampilkan form checkout (GET) atau proses checkout (POST).

    Keamanan:
    - Harga & total dihitung di server dari DB, TIDAK dari form.
    - Stok dikurangi dalam satu transaksi DB dengan row-level locking
      (SELECT … WITH FOR UPDATE) agar tidak oversell.
    - Keranjang dikosongkan setelah pesanan berhasil dibuat.
    """
    items = (
        CartItem.query
        .filter_by(user_id=current_user.id)
        .all()
    )
    if not items:
        flash('Keranjang kamu kosong.', 'warning')
        return redirect(url_for('keranjang.index'))

    if not current_user.has_shipping_details:
        flash('Lengkapi data penerima dan alamat di profil sebelum checkout.', 'warning')
        return redirect(url_for('profil.index'))

    shipping_configured = bool(
        current_app.config.get('BITESHIP_API_KEY')
        and current_app.config.get('SHIPPING_ORIGIN_POSTAL_CODE')
    )
    rates = []
    rates_error = None
    if shipping_configured:
        try:
            rates = biteship_rates(current_app.config, current_user, items)
        except IntegrationError as exc:
            rates_error = str(exc)
            _log('biteship_rates_failed', level='error', error=str(exc))

    form = CheckoutForm()
    if shipping_configured:
        form.courier.choices = [
            (
                rate['key'],
                f"{rate['courier'].upper()} {rate['service']} · "
                f"Estimasi {rate['duration'] or 'waktu mengikuti kurir'} · "
                f"Rp {rate['price']:,}",
            )
            for rate in rates
        ]
    midtrans_ready = bool(
        current_app.config.get('MIDTRANS_SERVER_KEY')
        and shipping_configured
        and rates
        and not rates_error
    )
    if midtrans_ready:
        form.payment_method.choices = [
            ('midtrans', 'Pembayaran online (QRIS, transfer bank, e-wallet)'),
            ('cod', 'Tunai saat pesanan diterima (COD)'),
        ]
    else:
        form.payment_method.choices = [
            ('bank_transfer', 'Transfer Bank (konfirmasi manual)'),
            ('qris', 'QRIS (konfirmasi manual)'),
            ('ewallet', 'E-Wallet (konfirmasi manual)'),
            ('cod', 'Tunai saat pesanan diterima (COD)'),
        ]
    if request.method == 'GET':
        if shipping_configured and rates:
            form.courier.data = rates[0]['key']
        if midtrans_ready:
            form.payment_method.data = 'midtrans'
        form.fragile_protection.data = any(
            item.product and item.product.is_fragile for item in items
        )

    if form.validate_on_submit():
        selected_rate = None
        if shipping_configured:
            selected_rate = next(
                (rate for rate in rates if rate['key'] == form.courier.data),
                None,
            )
            if rates_error or not selected_rate:
                flash('Tarif pengiriman tidak tersedia. Coba muat ulang checkout.', 'danger')
                return redirect(url_for('pesanan.checkout'))

        # --- Kunci seluruh proses dalam satu transaksi ---
        try:
            total = 0
            order_items_data = []
            contains_fragile = False

            for cart_item in items:
                # Ambil produk dengan row lock agar tidak race condition
                product = db.session.execute(
                    select(Product)
                    .where(Product.id == cart_item.product_id)
                    .with_for_update()
                ).scalar_one_or_none()

                if not product or not product.is_active:
                    db.session.rollback()
                    flash(
                        f'Produk "{cart_item.product.name if cart_item.product else cart_item.product_id}" '
                        'tidak tersedia. Harap perbarui keranjang.',
                        'danger',
                    )
                    return redirect(url_for('keranjang.index'))

                qty = cart_item.quantity
                contains_fragile = contains_fragile or product.is_fragile

                # Kurangi stok dengan lock
                if product.use_sizes:
                    ss = db.session.execute(
                        select(ProductSizeStock)
                        .where(
                            ProductSizeStock.product_id == product.id,
                            ProductSizeStock.size == cart_item.size,
                        )
                        .with_for_update()
                    ).scalar_one_or_none()

                    if not ss or ss.stock < qty:
                        db.session.rollback()
                        flash(
                            f'Stok ukuran {cart_item.size} untuk "{product.name}" tidak mencukupi '
                            f'(tersisa {ss.stock if ss else 0}).',
                            'danger',
                        )
                        return redirect(url_for('keranjang.index'))
                    ss.stock -= qty
                else:
                    if (product.stock or 0) < qty:
                        db.session.rollback()
                        flash(
                            f'Stok "{product.name}" tidak mencukupi (tersisa {product.stock}).', 'danger',
                        )
                        return redirect(url_for('keranjang.index'))
                    product.stock -= qty

                # Harga DARI DB, bukan dari form
                unit_price = product.price
                total += unit_price * qty

                order_items_data.append(
                    OrderItem(
                        product_id=product.id,
                        product_name=product.name,  # snapshot nama
                        product_description=product.description,
                        product_type=product.product_type,
                        product_color=product.color,
                        size=cart_item.size,
                        quantity=qty,
                        unit_price=unit_price,       # snapshot harga
                    )
                )

            # Buat order; biaya tambahan berasal dari konfigurasi server, bukan input browser.
            shipping_cost = selected_rate['price'] if selected_rate else 0
            shipping_discount = min(
                shipping_cost,
                max(0, current_app.config.get('CHECKOUT_SHIPPING_DISCOUNT_RP', 0)),
            )
            service_fee = max(0, current_app.config.get('CHECKOUT_SERVICE_FEE_RP', 0))
            fragile_protection = bool(
                contains_fragile and form.fragile_protection.data
            )
            fragile_fee = (
                max(0, current_app.config.get('FRAGILE_PACKING_FEE_RP', 0))
                if fragile_protection else 0
            )
            order = Order(
                user_id=current_user.id,
                status='menunggu_pembayaran',
                recipient_name=current_user.recipient_name.strip(),
                address=current_user.address.strip(),
                address_label=current_user.address_label,
                district=current_user.district.strip(),
                city=current_user.city.strip(),
                postal_code=current_user.postal_code.strip(),
                province=current_user.province.strip(),
                phone=current_user.phone.strip(),
                delivery_note=(current_user.delivery_note or '').strip() or None,
                courier=selected_rate['courier'] if selected_rate else form.courier.data,
                shipping_service=selected_rate['service'] if selected_rate else None,
                shipping_duration=selected_rate['duration'] if selected_rate else None,
                shipping_cost=shipping_cost,
                shipping_discount=shipping_discount,
                service_fee=service_fee,
                fragile_protection=fragile_protection,
                fragile_fee=fragile_fee,
                payment_method=form.payment_method.data,
                total_price=(
                    total + shipping_cost - shipping_discount + service_fee + fragile_fee
                ),
            )
            db.session.add(order)
            db.session.flush()  # dapatkan order.id sebelum commit

            for oi in order_items_data:
                oi.order_id = order.id
                db.session.add(oi)

            # Kosongkan keranjang
            CartItem.query.filter_by(user_id=current_user.id).delete()

            db.session.commit()

        except Exception:
            db.session.rollback()
            _log('checkout_failed', level='error')
            flash('Terjadi kesalahan saat memproses pesanan. Coba lagi.', 'danger')
            return redirect(url_for('keranjang.index'))

        _log('checkout_created', order_id=order.id, total=total, item_count=len(order_items_data))
        if order.payment_method == 'midtrans':
            return redirect(url_for('pesanan.bayar', order_id=order.id))
        flash('Pesanan berhasil dibuat! Silakan lakukan pembayaran.', 'success')
        return redirect(url_for('pesanan.detail', order_id=order.id))

    # GET — hitung total untuk preview
    total_preview = sum(
        item.product.price * item.quantity
        for item in items
        if item.product and item.product.is_active
    )
    selected_preview_rate = next(
        (rate for rate in rates if rate['key'] == form.courier.data),
        None,
    )
    shipping_preview = selected_preview_rate['price'] if selected_preview_rate else 0
    shipping_discount_preview = min(
        shipping_preview,
        max(0, current_app.config.get('CHECKOUT_SHIPPING_DISCOUNT_RP', 0)),
    )
    service_fee_preview = max(
        0, current_app.config.get('CHECKOUT_SERVICE_FEE_RP', 0),
    )
    fragile_selected = bool(
        any(item.product and item.product.is_fragile for item in items)
        and form.fragile_protection.data
    )
    fragile_fee_preview = (
        max(0, current_app.config.get('FRAGILE_PACKING_FEE_RP', 0))
        if fragile_selected else 0
    )
    return render_template(
        'pesanan/checkout.html',
        form=form,
        items=items,
        total=total_preview,
        shipping_rates=rates,
        shipping_configured=shipping_configured,
        rates_error=rates_error,
        shipping_total=shipping_preview,
        selected_preview_rate=selected_preview_rate,
        shipping_rate_map={rate['key']: rate for rate in rates},
        midtrans_ready=midtrans_ready,
        service_fee=service_fee_preview,
        shipping_discount=shipping_discount_preview,
        shipping_discount_cap=max(
            0, current_app.config.get('CHECKOUT_SHIPPING_DISCOUNT_RP', 0),
        ),
        contains_fragile=any(
            item.product and item.product.is_fragile for item in items
        ),
        fragile_fee=fragile_fee_preview,
        checkout_total=(
            total_preview + shipping_preview - shipping_discount_preview
            + service_fee_preview + fragile_fee_preview
        ),
    )


@bp.route('/<int:order_id>/bayar')
@login_required
def bayar(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    if order.user_id != current_user.id:
        log_access_denied('order_payment', order_id, reason='ownership')
        abort(403)
    if order.payment_method != 'midtrans' or order.status not in BUKTI_UPLOAD_ALLOWED:
        flash('Pembayaran online tidak tersedia untuk pesanan ini.', 'warning')
        return redirect(url_for('pesanan.detail', order_id=order_id))
    if order.payment_redirect_url and order.status == 'menunggu_pembayaran':
        return redirect(order.payment_redirect_url)
    try:
        if order.status == 'ditolak':
            order.status = 'menunggu_pembayaran'
            order.payment_transaction_id = None
            order.payment_token = None
            order.payment_redirect_url = None
            db.session.flush()
        transaction_id, token, redirect_url = create_midtrans_payment(
            current_app.config,
            order,
            order.items,
            url_for('pesanan.detail', order_id=order.id, _external=True),
        )
        order.payment_transaction_id = transaction_id
        order.payment_token = token
        order.payment_redirect_url = redirect_url
        db.session.commit()
    except IntegrationError as exc:
        db.session.rollback()
        _log('midtrans_payment_create_failed', level='error', order_id=order.id, error=str(exc))
        flash(f'Pembayaran belum dapat dibuat: {exc}', 'danger')
        return redirect(url_for('pesanan.detail', order_id=order.id))
    flash('Mengalihkan ke halaman pembayaran aman Midtrans.', 'success')
    return redirect(order.payment_redirect_url)


@bp.route('/webhooks/midtrans', methods=['POST'])
@csrf.exempt
def midtrans_notification():
    payload = request.get_json(silent=True) or {}
    server_key = current_app.config.get('MIDTRANS_SERVER_KEY', '')
    if not verify_midtrans_notification(payload, server_key):
        _log('midtrans_notification_rejected', level='warning')
        abort(403)

    transaction_id = str(payload.get('order_id', ''))
    order = Order.query.filter_by(payment_transaction_id=transaction_id).first()
    if not order or order.payment_method != 'midtrans':
        abort(404)
    try:
        gross_amount = float(payload.get('gross_amount', 'nan'))
    except (TypeError, ValueError):
        abort(400)
    if gross_amount != order.total_price:
        _log('midtrans_notification_amount_mismatch', level='warning', order_id=order.id)
        abort(400)

    transaction_status = payload.get('transaction_status')
    fraud_status = payload.get('fraud_status')
    if transaction_status == 'settlement' or (
        transaction_status == 'capture' and fraud_status == 'accept'
    ):
        if order.status in BUKTI_UPLOAD_ALLOWED:
            order.status = 'dibayar'
            order.payment_proof = None
            order.admin_note = 'Pembayaran terverifikasi otomatis oleh Midtrans.'
            db.session.commit()
            _log('midtrans_payment_settled', order_id=order.id)
    elif transaction_status in {'deny', 'cancel', 'expire', 'failure'}:
        if order.status == 'menunggu_pembayaran':
            order.status = 'ditolak'
            order.admin_note = 'Pembayaran tidak berhasil atau kedaluwarsa di Midtrans.'
            db.session.commit()
    return {'status': 'ok'}


@bp.route('/')
@login_required
def riwayat():
    """Daftar pesanan milik user sendiri. Anti-IDOR: filter by user_id."""
    page = request.args.get('page', 1, type=int)
    status = (request.args.get('status') or '').strip()
    query = Order.query.filter_by(user_id=current_user.id)
    if status and status in ['menunggu_pembayaran', 'menunggu_verifikasi', 'dibayar', 'ditolak', 'dikirim', 'selesai', 'dibatalkan']:
        query = query.filter(Order.status == status)
    pagination = (
        query.order_by(Order.created_at.desc())
        .paginate(page=page, per_page=10, error_out=False)
    )
    return render_template('pesanan/riwayat.html', pagination=pagination)


@bp.route('/<int:order_id>')
@login_required
def detail(order_id):
    """Detail pesanan. Hanya boleh diakses oleh pemilik. Anti-IDOR."""
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    if order.user_id != current_user.id:
        log_access_denied('order', order_id, reason='ownership')
        abort(403)
    return render_template('pesanan/detail.html', order=order)


@bp.route('/<int:order_id>/batalkan', methods=['POST'])
@login_required
def batalkan(order_id):
    """
    Customer membatalkan pesanan sendiri.
    Hanya boleh bila status ada di CUSTOMER_CANCELLABLE.
    Stok dikembalikan bila pesanan dibatalkan.
    Anti-IDOR: cek kepemilikan sebelum aksi.
    """
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    if order.user_id != current_user.id:
        log_access_denied('order', order_id, reason='ownership')
        abort(403)

    if order.status not in CUSTOMER_CANCELLABLE:
        flash('Pesanan ini tidak dapat dibatalkan.', 'warning')
        return redirect(url_for('pesanan.detail', order_id=order_id))

# Kembalikan stok
    try:
        restore_reserved_stock(order)
        order.status = 'dibatalkan'
        db.session.commit()

    except Exception:
        db.session.rollback()
        flash('Terjadi kesalahan saat membatalkan pesanan.', 'danger')
        return redirect(url_for('pesanan.detail', order_id=order_id))


    _log('order_status_changed', order_id=order.id, new_status='dibatalkan', actor='customer')
    flash('Pesanan berhasil dibatalkan.', 'success')
    return redirect(url_for('pesanan.riwayat'))



@bp.route('/<int:order_id>/upload-bukti', methods=['GET', 'POST'])
@login_required
@limiter.limit(
    '10 per hour',
    key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr,
)
def upload_bukti(order_id):
    """
    Customer mengunggah bukti bayar.
    Hanya boleh saat status menunggu_pembayaran.
    File disimpan di direktori privat (UPLOAD_PRIVATE).
    Anti-IDOR: cek kepemilikan sebelum aksi.
    Validasi: ekstensi + content-type + magic bytes (jpg/png/pdf, maks 2 MB).
    """
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    if order.user_id != current_user.id:
        log_access_denied('order_bukti', order_id, reason='ownership')
        abort(403)

    if order.status not in BUKTI_UPLOAD_ALLOWED:
        flash('Upload bukti bayar hanya diperbolehkan saat menunggu pembayaran.', 'warning')

        return redirect(url_for('pesanan.detail', order_id=order_id))

    if order.payment_method == 'cod':
        flash('Untuk pesanan COD, jangan unggah bukti transfer.', 'warning')
        return redirect(url_for('pesanan.detail', order_id=order_id))


    form = BuktiBayarForm()
    if form.validate_on_submit():
        file = form.bukti.data
        try:
            result = validate_image_upload(file, kind='bukti_bayar', max_bytes=MAX_PAYMENT_BYTES)
        except UploadRejected as e:
            _log(
                'file_upload_rejected',
                jenis='bukti_bayar',
                nama_asli=getattr(file, 'filename', ''),
                alasan=e.reason,
                order_id=order_id,
            )
            flash(f'File ditolak: {e.reason}', 'danger')
            return render_template('pesanan/upload_bukti.html', form=form, order=order), 400

        private_dir = current_app.config['UPLOAD_PRIVATE']
        ext = os.path.splitext(getattr(file, 'filename', '') or '')[1].lower()

        # Hapus file lama jika ada
        if order.payment_proof:
            old_path = os.path.join(private_dir, order.payment_proof)
            with contextlib.suppress(OSError):
                os.remove(old_path)

        # Simpan file baru
        if ext == '.pdf':
            # result adalah bytes mentah PDF
            fname = save_bytes(result, private_dir, '.pdf')
        else:
            # result adalah (bytes_raw, pil_image) — re-encode gambar
            _, img = result
            fname = reencode_and_save(img, private_dir)

        # Update order: simpan nama file dan ubah status ke menunggu_verifikasi
        order.payment_proof = fname
        order.status = 'menunggu_verifikasi'
        db.session.commit()

        _log(
            'bukti_bayar_uploaded',
            jenis='bukti_bayar',
            nama_asli=getattr(file, 'filename', ''),
            order_id=order_id,
            fname=fname,
        )
        _log('order_status_changed', order_id=order.id, new_status='menunggu_verifikasi', actor='customer')
        flash('Bukti bayar berhasil diunggah. Menunggu verifikasi admin.', 'success')
        return redirect(url_for('pesanan.detail', order_id=order_id))

    return render_template('pesanan/upload_bukti.html', form=form, order=order)


@bp.route('/<int:order_id>/bukti')
@login_required
def serve_bukti(order_id):
    """
    Sajikan file bukti bayar. Hanya untuk:
    - pemilik pesanan (customer)
    - admin
    Security headers: Content-Disposition attachment + X-Content-Type-Options nosniff.
    """
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)

    # Cek hak akses: hanya pemilik atau admin
    is_owner = order.user_id == current_user.id
    is_admin = current_user.role == 'admin'
    if not is_owner and not is_admin:
        log_access_denied('order_bukti', order_id, reason='ownership')
        abort(403)

    if not order.payment_proof:
        abort(404)

    private_dir = current_app.config['UPLOAD_PRIVATE']
    fname = order.payment_proof
    fpath = os.path.join(private_dir, fname)
    if not os.path.isfile(fpath):
        abort(404)

    # Tentukan MIME berdasarkan ekstensi file yang tersimpan
    ext = os.path.splitext(fname)[1].lower()
    mime = 'application/pdf' if ext == '.pdf' else 'image/jpeg'

    _log('bukti_bayar_download', order_id=order_id, fname=fname)

    response = send_from_directory(
        private_dir,
        fname,
        mimetype=mime,
        as_attachment=True,
        download_name=f'bukti_bayar_{order_id}{ext}',
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
