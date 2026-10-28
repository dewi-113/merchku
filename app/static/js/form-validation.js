// Validasi client-side untuk form bertanda data-validate.
//
// Aturan dibaca dari atribut HTML yang dirender WTForms (required, minlength,
// maxlength, min, max) ditambah atribut data-* khusus:
//   data-validate-email          format email
//   data-match="<id>"            harus sama dengan field lain (konfirmasi password)
//   data-greater-than="<id>"     angka harus lebih besar dari field lain
//   data-required-unless="<id>"  wajib diisi kecuali checkbox <id> dicentang
//   data-max-bytes / data-ext    batas ukuran & ekstensi file upload
//
// Ini hanya untuk kenyamanan pengguna: server tetap memvalidasi ulang
// semua input lewat WTForms, jadi aturan di sini harus sama dengan di forms.py.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function fieldLabel(field) {
  if (field.dataset.label) return field.dataset.label;
  const label = field.id && document.querySelector(`label[for="${field.id}"]`);
  return label ? label.textContent.trim().replace(/\s*\(.*\)$/, '') : 'Kolom ini';
}

function checkField(field, form) {
  const value = field.type === 'file' ? '' : field.value.trim();
  const label = fieldLabel(field);
  const other = (id) => form.querySelector(`#${id}`);

  if (field.type === 'file') {
    const file = field.files && field.files[0];
    if (!file) return field.required ? `${label} wajib dipilih.` : '';
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = (field.dataset.ext || '').split(',').filter(Boolean);
    if (allowed.length && !allowed.includes(ext)) return `Format file harus ${allowed.join(', ').toUpperCase()}.`;
    const maxBytes = Number(field.dataset.maxBytes || 0);
    if (maxBytes && file.size > maxBytes) return `Ukuran file maksimal ${Math.round(maxBytes / 1024 / 1024)} MB.`;
    return '';
  }

  const unless = field.dataset.requiredUnless && other(field.dataset.requiredUnless);
  const required = field.required || (unless && !unless.checked);
  if (!value) return required ? `${label} wajib diisi.` : '';

  if (field.type === 'number') {
    if (field.validity.badInput || Number.isNaN(Number(value))) return `${label} harus berupa angka.`;
    const num = Number(value);
    if (field.min !== '' && num < Number(field.min)) return `${label} minimal ${Number(field.min).toLocaleString('id-ID')}.`;
    if (field.max !== '' && num > Number(field.max)) return `${label} maksimal ${Number(field.max).toLocaleString('id-ID')}.`;
    const lower = field.dataset.greaterThan && other(field.dataset.greaterThan);
    if (lower && lower.value.trim() && num <= Number(lower.value)) {
      return `${label} harus lebih besar dari ${fieldLabel(lower).toLowerCase()}.`;
    }
  }

  if (field.minLength > 0 && value.length < field.minLength) return `${label} minimal ${field.minLength} karakter.`;
  if (field.maxLength > 0 && value.length > field.maxLength) return `${label} maksimal ${field.maxLength} karakter.`;
  if ('validateEmail' in field.dataset && !EMAIL_RE.test(value)) return 'Format email tidak valid, contoh: nama@email.com.';

  const match = field.dataset.match && other(field.dataset.match);
  if (match && field.value !== match.value) return `${label} tidak sama dengan ${fieldLabel(match).toLowerCase()}.`;
  return '';
}

function errorSlot(field) {
  const box = field.closest('.input-wrapper') || field;
  const container = box.parentElement;
  let slot = container.querySelector(`[data-error-for="${field.id}"]`);
  if (!slot) {
    slot = document.createElement('p');
    slot.className = 'js-field-error';
    slot.dataset.errorFor = field.id;
    slot.setAttribute('role', 'alert');
    box.after(slot);
  }
  return slot;
}

function showResult(field, message) {
  const slot = errorSlot(field);
  slot.textContent = message;
  slot.hidden = !message;
  field.classList.toggle('is-invalid', Boolean(message));
  field.setAttribute('aria-invalid', message ? 'true' : 'false');
  // Pesan error lama dari server untuk field yang sama disembunyikan agar tidak dobel
  slot.parentElement.querySelectorAll('.field-error').forEach((el) => { el.hidden = Boolean(message) || el.hidden; });
}

document.querySelectorAll('form[data-validate]').forEach((form) => {
  const fields = [...form.querySelectorAll('input, textarea, select')].filter(
    (el) => el.id && !['hidden', 'submit', 'checkbox', 'radio'].includes(el.type),
  );
  const touched = new Set();
  const validate = (field) => showResult(field, checkField(field, form));

  fields.forEach((field) => {
    field.addEventListener('blur', () => { touched.add(field); validate(field); });
    field.addEventListener(field.type === 'file' ? 'change' : 'input', () => {
      if (field.type === 'file') touched.add(field);
      if (touched.has(field)) validate(field);
      // Field yang bergantung pada field ini (konfirmasi password, harga coret) ikut dicek ulang
      fields.filter((f) => touched.has(f) && [f.dataset.match, f.dataset.greaterThan].includes(field.id)).forEach(validate);
    });
  });
  form.querySelectorAll('input[type=checkbox]').forEach((box) => {
    box.addEventListener('change', () => fields.filter((f) => f.dataset.requiredUnless === box.id && touched.has(f)).forEach(validate));
  });

  form.addEventListener('submit', (event) => {
    let firstInvalid = null;
    fields.forEach((field) => {
      touched.add(field);
      const message = checkField(field, form);
      showResult(field, message);
      if (message && !firstInvalid) firstInvalid = field;
    });
    if (firstInvalid) {
      event.preventDefault();
      firstInvalid.focus();
    }
  });
});
