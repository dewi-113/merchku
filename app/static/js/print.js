// Tombol cetak di halaman nota (file terpisah karena CSP melarang skrip inline).
document.querySelectorAll('[data-print]').forEach((b) => b.addEventListener('click', () => window.print()));
