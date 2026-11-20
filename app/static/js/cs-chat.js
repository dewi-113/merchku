// Customer Service "Merchy": widget mengambang + halaman /bantuan.
// Riwayat disimpan di sessionStorage (per tab) agar widget & halaman berbagi percakapan.
(() => {
  const STORAGE_KEY = 'merchku-cs-v1';
  const WELCOME = {
    role: 'assistant',
    text: 'Halo! Aku Merchy, CS Merchku. Mau cari produk, cek pesanan, atau tanya ongkir & pembayaran? Ketik aja di bawah ya.',
    suggestions: ['Cara belanja', 'Cek status pesanan', 'Produk diskon', 'Produk terlaris'],
  };
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

  const load = () => {
    try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || []; } catch { return []; }
  };
  const save = (items) => {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(-40))); } catch { /* abaikan */ }
  };
  const timeNow = () => new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function initRoom(root) {
    const list = root.querySelector('[data-cs-messages]');
    const chips = root.querySelector('[data-cs-suggestions]');
    const form = root.querySelector('[data-cs-form]');
    const input = form.querySelector('input');
    const url = root.dataset.csUrl;
    let items = load();
    let busy = false;

    function renderProducts(products) {
      const row = el('div', 'cs-products');
      products.forEach((product) => {
        const card = el('a', 'cs-product');
        card.href = product.url;
        const img = el('img');
        img.src = product.image;
        img.alt = '';
        img.loading = 'lazy';
        const body = el('span', 'cs-product-body');
        body.append(el('span', 'cs-product-name', product.name));
        const price = el('span', 'cs-product-price', product.price);
        if (product.old_price) price.append(el('del', '', product.old_price));
        body.append(price);
        body.append(el('span', 'cs-product-meta', product.stock > 0 ? `Stok ${product.stock} · ${product.shop}` : 'Stok habis'));
        if (product.discount) {
          const tag = el('span', 'cs-product-tag', `-${product.discount}%`);
          card.append(tag);
        }
        card.append(img, body);
        row.append(card);
      });
      return row;
    }

    function renderItem(item) {
      const row = el('div', `cs-row ${item.role === 'user' ? 'is-user' : 'is-bot'}`);
      const bubble = el('div', 'cs-bubble');
      bubble.append(el('div', 'cs-text', item.text));
      if (item.links?.length) {
        const links = el('div', 'cs-links');
        item.links.forEach((link) => {
          const anchor = el('a', 'cs-link', link.label);
          anchor.href = link.url;
          links.append(anchor);
        });
        bubble.append(links);
      }
      const meta = el('span', 'cs-time', item.time || '');
      if (item.role === 'assistant' && item.source === 'ai') meta.textContent += ' · AI';
      bubble.append(meta);
      row.append(bubble);
      if (item.products?.length) row.append(renderProducts(item.products));
      list.append(row);
    }

    function renderSuggestions(suggestions) {
      chips.replaceChildren();
      (suggestions || []).forEach((label) => {
        const chip = el('button', 'cs-chip', label);
        chip.type = 'button';
        chip.addEventListener('click', () => send(label));
        chips.append(chip);
      });
    }

    function renderAll() {
      list.replaceChildren();
      const all = items.length ? items : [{ ...WELCOME, time: timeNow() }];
      all.forEach(renderItem);
      list.lastElementChild?.classList.add('is-new');
      const lastBot = [...all].reverse().find((item) => item.role === 'assistant');
      renderSuggestions(lastBot?.suggestions || WELCOME.suggestions);
      list.scrollTop = list.scrollHeight;
    }

    async function send(text) {
      const message = (text || '').trim();
      if (!message || busy) return;
      busy = true;
      if (!items.length) items.push({ ...WELCOME, time: timeNow() });
      const history = items.map(({ role, text: body }) => ({ role, text: body }));
      items.push({ role: 'user', text: message, time: timeNow() });
      save(items);
      renderAll();
      chips.replaceChildren();
      const typing = el('div', 'cs-row is-bot cs-typing');
      typing.innerHTML = '<div class="cs-bubble"><span></span><span></span><span></span></div>';
      list.append(typing);
      list.scrollTop = list.scrollHeight;

      let reply;
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
          body: JSON.stringify({ message, history }),
        });
        if (response.status === 429) throw new Error('Terlalu banyak pertanyaan, tunggu sebentar ya.');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Gagal mengirim pertanyaan.');
        reply = {
          role: 'assistant', text: data.reply, products: data.products, links: data.links,
          suggestions: data.suggestions, source: data.source, time: timeNow(),
        };
      } catch (error) {
        reply = {
          role: 'assistant', time: timeNow(), suggestions: WELCOME.suggestions,
          text: error.message && !error.message.includes('JSON') ? error.message : 'Maaf, koneksi sedang bermasalah. Coba lagi ya.',
        };
      }
      items.push(reply);
      save(items);
      busy = false;
      renderAll();
    }

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const value = input.value;
      input.value = '';
      send(value);
    });
    root.querySelector('[data-cs-reset]')?.addEventListener('click', () => {
      items = [];
      save(items);
      renderAll();
    });
    window.addEventListener('storage', () => { items = load(); renderAll(); });
    root.csRender = () => { items = load(); renderAll(); };
    renderAll();
    return { focus: () => input.focus() };
  }

  document.querySelectorAll('[data-cs-root]').forEach((root) => {
    const room = initRoom(root);
    const panel = root.closest('[data-cs-panel]');
    if (!panel) return;
    const fab = document.querySelector('[data-cs-open]');
    const setOpen = (open) => {
      panel.hidden = !open;
      fab?.setAttribute('aria-expanded', String(open));
      fab?.classList.toggle('is-open', open);
      if (open) { root.csRender(); room.focus(); }
    };
    fab?.addEventListener('click', () => setOpen(panel.hidden));
    root.querySelector('[data-cs-close]')?.addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !panel.hidden) setOpen(false); });
  });
})();
