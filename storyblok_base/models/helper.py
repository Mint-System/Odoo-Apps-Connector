def get_image_file_type(file):
    magic_numbers = {
        "png": bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
        "jpg": bytes([0xFF, 0xD8, 0xFF]),
        "pdf": bytes([0x25, 0x50, 0x44, 0x46]),
        "gif": bytes([0x47, 0x49, 0x46]),
        "bmp": bytes([0x42, 0x4D]),
        "tif": bytes([0x49, 0x49, 0x2A, 0x00]),
        "webp": bytes([0x52, 0x49, 0x46, 0x46]),
    }
    file_start = file[:16]

    # Check for standard file types
    for key, value in magic_numbers.items():
        if file_start.startswith(value):
            return key

    # Check for SVG files by looking for XML declaration or <svg> tag
    file_start_str = file_start.decode(errors="ignore")
    if file_start_str.strip().startswith("<?xml") or "<svg" in file_start_str:
        return "svg"

    return "unknown"
