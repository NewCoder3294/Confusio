from mendacity.mime import guess_image_mime


def test_png_magic():
    assert guess_image_mime(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) == "image/png"


def test_jpeg_magic():
    assert guess_image_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == "image/jpeg"
