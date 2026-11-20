const footerTop = document.getElementById('footerTop');
if (footerTop) {
  footerTop.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

const chatMessages = document.querySelector('[data-chat-messages]');
if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;

// Pencarian di daftar percakapan
document.querySelector('[data-chat-search]')?.addEventListener('input', (event) => {
  const keyword = event.target.value.trim().toLowerCase();
  document.querySelectorAll('[data-chat-name]').forEach((item) => {
    item.hidden = keyword && !item.dataset.chatName.includes(keyword);
  });
});

// Ruang chat penjual ↔ pembeli: kirim tanpa reload + pesan baru masuk otomatis
const chatRoom = document.querySelector('[data-chat-room]');
if (chatRoom && chatMessages) {
  const chatForm = chatRoom.querySelector('[data-chat-form]');
  const chatInput = chatForm.querySelector('textarea');
  const sendButton = chatForm.querySelector('.chat-send');
  const emojiPanel = chatRoom.querySelector('[data-chat-emoji]');
  const emojiToggle = chatRoom.querySelector('[data-chat-emoji-toggle]');
  const MAX_INPUT_HEIGHT = 120;
  let lastId = Number(chatRoom.dataset.lastId || 0);
  let sending = false;

  // Tinggi textarea mengikuti isi. Tambahkan tebal border (box-sizing: border-box),
  // kalau tidak isi selalu kurang 2px → muncul scrollbar dengan panah atas/bawah.
  const autosize = () => {
    chatInput.style.height = 'auto';
    const border = chatInput.offsetHeight - chatInput.clientHeight;
    const wanted = chatInput.scrollHeight + border;
    chatInput.style.height = `${Math.min(wanted, MAX_INPUT_HEIGHT)}px`;
    chatInput.style.overflowY = wanted > MAX_INPUT_HEIGHT ? 'auto' : 'hidden';
    sendButton.classList.toggle('is-ready', chatInput.value.trim().length > 0);
  };
  const scrollToBottom = () => { chatMessages.scrollTop = chatMessages.scrollHeight; };

  const otherAvatar = () => {
    const holder = document.createElement('span');
    holder.className = 'chat-row-avatar';
    holder.setAttribute('aria-hidden', 'true');
    if (chatMessages.dataset.otherAvatar) {
      const img = document.createElement('img');
      img.src = chatMessages.dataset.otherAvatar;
      img.alt = '';
      holder.append(img);
    } else {
      holder.textContent = chatMessages.dataset.otherInitial || '';
    }
    return holder;
  };

  const addMessage = (message) => {
    if (message.id <= lastId) return; // sudah tampil (mis. dari polling)
    chatMessages.querySelector('.chat-empty')?.remove();
    const days = chatMessages.querySelectorAll('.chat-day');
    let newDay = false;
    if (!days.length || days[days.length - 1].dataset.day !== message.day) {
      const day = document.createElement('div');
      day.className = 'chat-day';
      day.dataset.day = message.day;
      day.innerHTML = '<span></span>';
      day.firstChild.textContent = message.day;
      chatMessages.append(day);
      newDay = true;
    }
    const sender = message.mine ? 'me' : 'them';
    const previous = chatMessages.lastElementChild;
    const first = newDay || !previous?.classList.contains('chat-message-row') || previous.dataset.sender !== sender;

    const row = document.createElement('div');
    row.className = `chat-message-row ${message.mine ? 'is-mine' : 'is-theirs'} is-new`;
    row.dataset.msgId = message.id;
    row.dataset.sender = sender;
    if (first) row.dataset.first = '';
    if (!message.mine) {
      const avatar = otherAvatar();
      if (!first) avatar.replaceChildren();
      row.append(avatar);
    }
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    const body = document.createElement('div');
    body.className = 'chat-message-body';
    body.textContent = message.body;
    const time = document.createElement('time');
    time.className = 'chat-message-time';
    time.textContent = message.time;
    if (message.mine) {
      const tick = document.createElement('span');
      tick.className = 'chat-tick';
      tick.textContent = ' ✓✓';
      time.append(tick);
    }
    bubble.append(body, time);
    row.append(bubble);
    chatMessages.append(row);
    lastId = Math.max(lastId, message.id);
    scrollToBottom();
  };

  const insertText = (text) => {
    const start = chatInput.selectionStart ?? chatInput.value.length;
    const end = chatInput.selectionEnd ?? chatInput.value.length;
    chatInput.value = chatInput.value.slice(0, start) + text + chatInput.value.slice(end);
    const caret = start + text.length;
    chatInput.setSelectionRange(caret, caret);
    autosize();
  };

  chatRoom.querySelectorAll('[data-chat-fill]').forEach((button) => {
    button.addEventListener('click', () => {
      chatInput.value = button.dataset.chatFill;
      autosize();
      chatInput.focus();
    });
  });
  chatRoom.querySelector('[data-chat-product-close]')?.addEventListener('click', (event) => {
    event.target.closest('[data-chat-product]')?.remove();
  });
  emojiToggle?.addEventListener('click', () => {
    const open = emojiPanel.hidden;
    emojiPanel.hidden = !open;
    emojiToggle.setAttribute('aria-expanded', String(open));
    emojiToggle.classList.toggle('is-active', open);
  });
  emojiPanel?.querySelectorAll('[data-emoji]').forEach((button) => {
    button.addEventListener('click', () => {
      insertText(button.dataset.emoji);
      chatInput.focus();
    });
  });
  chatInput.addEventListener('input', autosize);
  // Saat keyboard HP muncul, tetap tampilkan pesan terakhir.
  chatInput.addEventListener('focus', () => window.setTimeout(scrollToBottom, 300));
  window.visualViewport?.addEventListener('resize', () => {
    if (document.activeElement === chatInput) scrollToBottom();
  });
  chatInput.addEventListener('keydown', (event) => {
    // Enter = kirim, Shift+Enter = baris baru (di HP keyboard tetap baris baru)
    if (event.key === 'Enter' && !event.shiftKey && window.matchMedia('(hover: hover)').matches) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });
  chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = chatInput.value.trim();
    if (!text || sending) return;
    sending = true;
    sendButton.classList.add('is-sending');
    try {
      const response = await fetch(chatForm.action || window.location.pathname, {
        method: 'POST',
        headers: { 'X-Requested-With': 'fetch' },
        body: new FormData(chatForm),
      });
      if (response.status === 429) throw new Error('Terlalu banyak pesan dalam waktu singkat. Coba lagi nanti ya.');
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || 'Pesan gagal dikirim.');
      chatInput.value = '';
      autosize();
      addMessage(data.message);
      chatRoom.querySelector('[data-chat-product]')?.remove();
      if (emojiPanel && !emojiPanel.hidden) emojiToggle.click();
      chatInput.focus();
    } catch (error) {
      window.alert(error.message || 'Pesan gagal dikirim.');
    } finally {
      sending = false;
      sendButton.classList.remove('is-sending');
    }
  });
  autosize();

  const poll = async () => {
    if (document.hidden) return;
    try {
      const response = await fetch(`${chatRoom.dataset.pollUrl}?after=${lastId}`);
      if (!response.ok) return;
      const data = await response.json();
      data.messages.forEach(addMessage);
    } catch { /* koneksi putus sesaat: coba lagi di putaran berikutnya */ }
  };
  window.setInterval(poll, 4000);
}

const navItems = document.querySelectorAll('[data-nav]');
const liquid = document.getElementById('navLiquid');
const track = document.getElementById('navLinks');
let target = null;
let cur = { x: 0, w: 0 };
let active = null;

function rectIn(element) {
  const rect = element.getBoundingClientRect();
  const trackRect = track.getBoundingClientRect();
  return { x: rect.left - trackRect.left, w: rect.width };
}

function aimAt(element) {
  if (!element || !liquid || !track) return;
  target = rectIn(element);
  if (!liquid.classList.contains('on')) {
    cur.x = target.x;
    cur.w = target.w;
    liquid.classList.add('on');
  }
}

if (track && liquid) {
  const path = window.location.pathname;
  navItems.forEach((link) => {
    const href = link.getAttribute('href');
    if ((href && path.startsWith(href) && href !== '/') || (href === '/' && path === '/')) {
      link.classList.add('active');
      active = link;
    }
  });
}

// Indikator liquid disembunyikan oleh tema marketplace; jangan jalankan loop
// animasi (requestAnimationFrame terus-menerus) bila elemennya tidak tampil.
if (track && liquid && window.getComputedStyle(liquid).display !== 'none') {
  if (active) aimAt(active);

  navItems.forEach((link) => {
    link.addEventListener('mouseenter', () => aimAt(link));
    link.addEventListener('focus', () => aimAt(link));
    link.addEventListener('mouseleave', () => aimAt(active));
  });

  let prevX = 0;
  function liquidTick() {
    if (target) {
      const dx = target.x - cur.x;
      cur.x += dx * 0.14;
      cur.w += (target.w - cur.w) * 0.18;
      const speed = Math.abs(cur.x - prevX);
      prevX = cur.x;
      const stretch = Math.min(speed * 0.035, 0.5);
      const squash = Math.min(speed * 0.012, 0.16);
      liquid.style.width = `${cur.w}px`;
      liquid.style.transform = `translateX(${cur.x}px) scaleX(${1 + stretch}) scaleY(${1 - squash})`;
    }
    window.requestAnimationFrame(liquidTick);
  }
  liquidTick();
  window.addEventListener('resize', () => {
    if (active) {
      target = rectIn(active);
      cur.x = target.x;
      cur.w = target.w;
    }
  });
}

const hamburger = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobileMenu');
if (hamburger && mobileMenu) {
  const setMenu = (open) => {
    hamburger.classList.toggle('open', open);
    mobileMenu.classList.toggle('open', open);
    hamburger.setAttribute('aria-expanded', String(open));
  };
  hamburger.addEventListener('click', () => setMenu(!mobileMenu.classList.contains('open')));

  document.addEventListener('click', (event) => {
    if (!hamburger.contains(event.target) && !mobileMenu.contains(event.target)) setMenu(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setMenu(false);
  });
  // Menu desktop tidak boleh tertinggal terbuka saat layar diperlebar.
  window.matchMedia('(min-width: 992px)').addEventListener('change', (event) => {
    if (event.matches) setMenu(false);
  });
}

document.querySelectorAll('.nav-dropdown[data-dd]').forEach((dropdown) => {
  const toggle = dropdown.querySelector('.dd-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const shouldOpen = !dropdown.classList.contains('open');
    document.querySelectorAll('.nav-dropdown.open').forEach((openDropdown) => {
      openDropdown.classList.remove('open');
    });
    if (shouldOpen) dropdown.classList.add('open');
  });
});

document.addEventListener('click', (event) => {
  if (!event.target.closest('.nav-dropdown[data-dd]')) {
    document.querySelectorAll('.nav-dropdown.open').forEach((dropdown) => {
      dropdown.classList.remove('open');
    });
  }
});

// Navbar kini full-width; cukup beri bayangan saat halaman di-scroll.
// (Sebelumnya top/width diubah inline sehingga navbar menyusut & bergeser.)
const navbar = document.getElementById('glassNav');
if (navbar) {
  const updateNavShadow = () => navbar.classList.toggle('is-scrolled', window.scrollY > 8);
  window.addEventListener('scroll', updateNavShadow, { passive: true });
  updateNavShadow();
}

// Tabel lebar di HP: bungkus dengan .table-responsive agar halaman tidak ikut geser horizontal.
document.querySelectorAll('main table').forEach((table) => {
  if (table.closest('.table-responsive')) return;
  const wrapper = document.createElement('div');
  wrapper.className = 'table-responsive';
  table.parentNode.insertBefore(wrapper, table);
  wrapper.appendChild(table);
});

document.querySelectorAll('[data-dismiss-flash]').forEach((button) => {
  button.addEventListener('click', () => button.closest('.flash-item')?.remove());
});

window.setTimeout(() => {
  document.querySelectorAll('.flash-item').forEach((element) => {
    element.style.transition = 'opacity 0.5s ease';
    element.style.opacity = '0';
    window.setTimeout(() => element.remove(), 500);
  });
}, 4000);

document.querySelectorAll('[data-password-toggle]').forEach((toggle) => {
  toggle.addEventListener('click', () => {
    const input = document.getElementById(toggle.dataset.passwordToggle);
    if (!input) return;
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    toggle.textContent = visible ? 'Sembunyi' : 'Lihat';
    toggle.setAttribute('aria-label', visible ? 'Sembunyikan password' : 'Tampilkan password');
    toggle.setAttribute('aria-pressed', String(visible));
    input.focus();
  });
});

document.querySelectorAll('[data-quantity-step]').forEach((button) => {
  button.addEventListener('click', () => {
    const form = button.closest('form');
    const quantity = form?.querySelector('[data-product-quantity]');
    if (!quantity) return;
    const next = Number(quantity.value || 1) + Number(button.dataset.quantityStep);
    quantity.value = String(Math.min(Number(quantity.max), Math.max(1, next)));
  });
});

document.querySelectorAll('[data-cart-step]').forEach((button) => {
  button.addEventListener('click', () => {
    const quantity = button.closest('.cart-stepper')?.querySelector('input[name="quantity"]');
    if (!quantity) return;
    const min = Number(quantity.min || 1);
    const max = Number(quantity.max || 99);
    const next = Number(quantity.value || min) + Number(button.dataset.cartStep);
    quantity.value = String(Math.min(max, Math.max(min, next)));
  });
});

// Keranjang: pilih produk (per item / per toko / semua) untuk checkout sebagian.
(() => {
  const form = document.getElementById('cartCheckoutForm');
  if (!form) return;
  const items = [...document.querySelectorAll('[data-cart-check]')];
  const shopToggles = [...document.querySelectorAll('[data-cart-shop-toggle]')];
  const allToggles = [...document.querySelectorAll('[data-cart-all-toggle]')];
  const totalEl = document.getElementById('cartSelectedTotal');
  const countEl = document.getElementById('cartSelectedCount');
  const submit = form.querySelector('[type="submit"]');
  const rupiah = (n) => 'Rp ' + n.toLocaleString('id-ID');

  const syncToggle = (toggle, boxes) => {
    const checked = boxes.filter((b) => b.checked).length;
    toggle.checked = boxes.length > 0 && checked === boxes.length;
    toggle.indeterminate = checked > 0 && checked < boxes.length;
  };

  const refresh = () => {
    let total = 0;
    let count = 0;
    items.forEach((box) => {
      box.closest('.cart-item')?.classList.toggle('is-unselected', !box.checked);
      if (box.checked) {
        total += Number(box.dataset.subtotal || 0);
        count += 1;
      }
    });
    shopToggles.forEach((toggle) => {
      syncToggle(toggle, items.filter((b) => b.dataset.shop === toggle.dataset.shop));
    });
    allToggles.forEach((toggle) => syncToggle(toggle, items));
    if (totalEl) totalEl.textContent = rupiah(total);
    if (countEl) countEl.textContent = String(count);
    if (submit) submit.disabled = count === 0;
  };

  items.forEach((box) => box.addEventListener('change', refresh));
  shopToggles.forEach((toggle) => toggle.addEventListener('change', () => {
    items.filter((b) => b.dataset.shop === toggle.dataset.shop)
      .forEach((b) => { b.checked = toggle.checked; });
    refresh();
  }));
  allToggles.forEach((toggle) => toggle.addEventListener('change', () => {
    items.forEach((b) => { b.checked = toggle.checked; });
    refresh();
  }));
  refresh();
})();

document.querySelectorAll('[data-product-size]').forEach((sizeOption) => {
  sizeOption.addEventListener('change', () => {
    const form = sizeOption.closest('form');
    const quantity = form?.querySelector('[data-product-quantity]');
    const stockHint = form?.querySelector('[data-stock-hint]');
    const stock = Number(sizeOption.dataset.stock);
    if (!quantity || !stock) return;
    const maximum = Math.min(stock || 1, 99);
    quantity.max = String(maximum);
    if (Number(quantity.value) > maximum) quantity.value = String(maximum);
    if (stockHint) stockHint.textContent = `${stock} stok tersedia · Maks. ${maximum}`;
  });
});

// Form produk (admin & penjual): tampilkan stok per ukuran atau stok tunggal.
// Dipindah dari <script> inline yang diblokir Content-Security-Policy.
const useSizes = document.getElementById('use_sizes');
const stockBySize = document.getElementById('stock-ukuran');
const stockSingle = document.getElementById('stock-tunggal');
if (useSizes && stockBySize && stockSingle) {
  const toggleStock = () => {
    stockBySize.style.display = useSizes.checked ? '' : 'none';
    stockSingle.style.display = useSizes.checked ? 'none' : '';
  };
  useSizes.addEventListener('change', toggleStock);
  toggleStock();
}

// Ringkasan checkout: hitung ulang total saat kurir / proteksi dipilih.
const checkoutForm = document.querySelector('[data-checkout-form]');
if (checkoutForm) {
  const money = (value) => `Rp ${Math.max(0, value).toLocaleString('id-ID')}`;
  const { dataset } = checkoutForm;
  const subtotal = Number(dataset.subtotal || 0);
  const serviceFee = Number(dataset.serviceFee || 0);
  const shippingDiscountCap = Number(dataset.shippingDiscountCap || 0);
  const fragileFee = Number(dataset.fragileFee || 0);
  const containsFragile = dataset.containsFragile === '1';
  const shippingValue = document.getElementById('checkout-shipping-value');
  const discountValue = document.getElementById('checkout-discount-value');
  const totalValue = document.getElementById('checkout-total-value');
  const fragileValue = document.getElementById('checkout-fragile-value');

  const updateSummary = () => {
    const selectedShipping = checkoutForm.querySelector('[data-shipping-choice]:checked');
    const hasLiveRate = selectedShipping && selectedShipping.dataset.shippingPrice !== '';
    const shipping = hasLiveRate ? Number(selectedShipping.dataset.shippingPrice) : 0;
    const discount = Math.min(shipping, shippingDiscountCap);
    const protectionSelected = containsFragile
      && checkoutForm.querySelector('[data-fragile-protection]')?.checked;
    const packingFee = protectionSelected ? fragileFee : 0;

    if (shippingValue) {
      shippingValue.textContent = hasLiveRate ? money(shipping) : 'Dikonfirmasi admin';
    }
    if (discountValue) discountValue.textContent = `- ${money(discount)}`;
    if (fragileValue) {
      fragileValue.textContent = protectionSelected ? money(packingFee) : 'Tidak dipilih';
    }
    if (totalValue) {
      totalValue.textContent = money(subtotal + shipping - discount + serviceFee + packingFee);
    }
  };

  checkoutForm.querySelectorAll('[data-shipping-choice], [data-fragile-protection]')
    .forEach((input) => input.addEventListener('change', updateSummary));
  updateSummary();
}

// Banner slider beranda: geser otomatis, titik indikator, jeda saat disentuh/hover.
document.querySelectorAll('[data-carousel]').forEach((carousel) => {
  const carouselTrack = carousel.querySelector('[data-carousel-track]');
  const dotsWrap = carousel.querySelector('[data-carousel-dots]');
  const slides = carouselTrack ? [...carouselTrack.children] : [];
  if (slides.length < 2) return;

  const dots = slides.map((_, index) => {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.setAttribute('aria-label', `Banner ${index + 1}`);
    dot.addEventListener('click', () => goTo(index));
    dotsWrap?.appendChild(dot);
    return dot;
  });
  const currentIndex = () => Math.round(carouselTrack.scrollLeft / carouselTrack.clientWidth);
  const markActive = () => dots.forEach((dot, index) => dot.classList.toggle('active', index === currentIndex()));
  function goTo(index) {
    carouselTrack.scrollTo({ left: index * carouselTrack.clientWidth });
  }

  let timer = null;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const start = () => {
    if (reduceMotion) return;
    stop();
    timer = window.setInterval(() => goTo((currentIndex() + 1) % slides.length), 4500);
  };
  const stop = () => { if (timer) window.clearInterval(timer); timer = null; };

  carouselTrack.addEventListener('scroll', markActive, { passive: true });
  carousel.addEventListener('mouseenter', stop);
  carousel.addEventListener('mouseleave', start);
  carousel.addEventListener('touchstart', stop, { passive: true });
  carousel.addEventListener('touchend', start);
  markActive();
  start();
});

document.querySelectorAll('[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// Banner "Pasang Merchku": pakai prompt instal bawaan browser bila tersedia,
// kalau tidak tampilkan cara menambahkan ke layar utama.
let installPrompt = null;
window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  installPrompt = event;
});
document.querySelectorAll('[data-install-app]').forEach((button) => {
  button.addEventListener('click', async (event) => {
    event.preventDefault();
    if (installPrompt) {
      installPrompt.prompt();
      await installPrompt.userChoice.catch(() => null);
      installPrompt = null;
      return;
    }
    const standalone = window.matchMedia('(display-mode: standalone)').matches;
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    window.alert(standalone
      ? 'Merchku sudah terpasang di HP kamu 🎉'
      : ios
        ? 'Di Safari: ketuk tombol Bagikan (kotak dengan panah ke atas), lalu pilih "Tambah ke Layar Utama".'
        : 'Buka menu browser (⋮) lalu pilih "Instal aplikasi" atau "Tambahkan ke layar utama".');
  });
});

// Foto profil: pilih dari galeri/kamera, diperkecil di browser (foto kamera HP
// biasanya > 1 MB), lalu langsung diunggah.
function shrinkImage(file, maxSide = 720) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      const img = new Image();
      img.onerror = reject;
      img.onload = () => {
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.86);
        canvas.toBlob((blob) => (blob ? resolve({ blob, dataUrl }) : reject(new Error('gagal'))), 'image/jpeg', 0.86);
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

document.querySelectorAll('[data-avatar-form]').forEach((form) => {
  const input = form.querySelector('input[type="file"]');
  input?.addEventListener('change', async () => {
    const file = input.files?.[0];
    if (!file) return;
    if (!/^image\/(jpeg|png|webp|heic|heif)$/i.test(file.type) && !/\.(jpe?g|png)$/i.test(file.name)) {
      window.alert('Pilih foto berformat JPG atau PNG ya.');
      input.value = '';
      return;
    }
    form.classList.add('is-uploading');
    try {
      const { blob, dataUrl } = await shrinkImage(file);
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], 'avatar.jpg', { type: 'image/jpeg' }));
      input.files = transfer.files;
      const preview = form.querySelector('[data-avatar-preview]');
      if (preview) {
        const img = document.createElement('img');
        img.className = preview.className;
        img.alt = 'Foto profil';
        img.src = dataUrl;
        img.dataset.avatarPreview = '';
        preview.replaceWith(img);
      }
    } catch {
      // Browser tidak bisa memproses (mis. HEIC): kirim file aslinya bila cukup kecil.
      if (file.size > 1024 * 1024) {
        form.classList.remove('is-uploading');
        window.alert('Foto tidak bisa diproses atau lebih dari 1 MB. Coba foto lain ya.');
        input.value = '';
        return;
      }
    }
    form.requestSubmit();
  });
});
