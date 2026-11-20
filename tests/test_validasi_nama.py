import pytest

from app.core.validators import _FORBIDDEN_RE, shop_name_valid


@pytest.mark.parametrize('name', ['Merch Kampus Store', 'Ruang Kreatif Merch', "Toko Budi's & Co.", 'Kafé 21'])
def test_nama_toko_valid(name):
    assert shop_name_valid(name)


@pytest.mark.parametrize('name', ['{{7*7}}sst', '<script>x</script>', '{% raw %}', '${7*7}', '_toko', '-toko'])
def test_nama_toko_ditolak(name):
    assert not shop_name_valid(name)


@pytest.mark.parametrize('text', ['{{7*7}}', '<b>', '`id`', '${x}'])
def test_no_markup_ditolak(text):
    assert _FORBIDDEN_RE.search(text)


def test_no_markup_teks_biasa_lolos():
    assert not _FORBIDDEN_RE.search('Kaos Oversize 100% Cotton - Hitam / Putih #1')
