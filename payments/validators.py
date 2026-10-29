import re
import uuid

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
IMAGE_EXTENSIONS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}
ACCOUNT_NUMBER_PATTERN = re.compile(r"^[0-9]{6,34}$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
MAX_PAYEES_PER_REQUEST = 5
MAX_PAYEE_NAME_LENGTH = 100


def validate_uploaded_image(uploaded_file):
    if uploaded_file.size > MAX_IMAGE_SIZE:
        raise serializers.ValidationError("Image size must not exceed 5 MB.")

    try:
        with Image.open(uploaded_file) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise serializers.ValidationError("Upload a valid image file.") from exc

    if width * height > MAX_IMAGE_PIXELS:
        raise serializers.ValidationError("Image dimensions are too large.")

    extension = IMAGE_EXTENSIONS.get(image_format or "")
    if extension is None:
        raise serializers.ValidationError("Only PNG, JPG, and WebP images are allowed.")

    uploaded_file.seek(0)
    uploaded_file.name = f"{uuid.uuid4().hex}.{extension}"
    return uploaded_file


def validate_account_number(value):
    value = re.sub(r"\s+", "", value or "").strip()
    if not ACCOUNT_NUMBER_PATTERN.match(value):
        raise serializers.ValidationError(
            "Enter a valid account number using 6 to 34 digits."
        )
    return value


def validate_ifsc(value):
    value = re.sub(r"\s+", "", value or "").strip().upper()
    if not IFSC_PATTERN.match(value):
        raise serializers.ValidationError(
            "Enter a valid IFSC code in the format ABCD0123456."
        )
    return value


def validate_payee_name(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) < 2:
        raise serializers.ValidationError("Enter the payee account name.")
    return value
