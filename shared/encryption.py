"""
encryption.py

Centralized encryption/decryption functionality for the DBMS test runner system.
Uses Fernet symmetric encryption for test files and results.
"""

from pathlib import Path
from shared.logger import get_logger

logger = get_logger(__name__)

try:
    from cryptography.fernet import Fernet  # type: ignore
except ImportError:
    Fernet = None  # type: ignore


def get_or_create_key(key_path: Path) -> bytes:
    """
    Load or generate a new encryption key.

    Args:
        key_path: Path to the encryption key file

    Returns:
        Encryption key as bytes

    Raises:
        ImportError: If cryptography library is not installed
        IOError: If key file cannot be read or written
    """
    if Fernet is None:
        raise ImportError(
            "Cryptography library not installed. Run: pip install cryptography"
        )

    if key_path.exists():
        # Existing key will be used
        return key_path.read_bytes()

    logger.info(f"Generating new encryption key at {key_path}")
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def encrypt_data(data: bytes, key: bytes) -> bytes:
    """
    Encrypt data using Fernet symmetric encryption.

    Args:
        data: Data to encrypt as bytes
        key: Encryption key

    Returns:
        Encrypted data as bytes

    Raises:
        ImportError: If cryptography library is not installed
        Exception: If encryption fails
    """
    if Fernet is None:
        raise ImportError(
            "Cryptography library not installed. Run: pip install cryptography"
        )

    try:
        fernet = Fernet(key)
        encrypted = fernet.encrypt(data)
        # encryption performed
        return encrypted
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise


def decrypt_data(encrypted_data: bytes, key: bytes) -> bytes:
    """
    Decrypt data using Fernet symmetric encryption.

    Args:
        encrypted_data: Encrypted data as bytes
        key: Encryption key

    Returns:
        Decrypted data as bytes

    Raises:
        ImportError: If cryptography library is not installed
        Exception: If decryption fails (wrong key, corrupted data, etc.)
    """
    if Fernet is None:
        raise ImportError(
            "Cryptography library not installed. Run: pip install cryptography"
        )

    try:
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_data)
        # decryption performed
        return decrypted
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise


def encrypt_string(text: str, key: bytes, encoding: str = "utf-8") -> bytes:
    """
    Encrypt a string.

    Args:
        text: String to encrypt
        key: Encryption key
        encoding: String encoding (default: utf-8)

    Returns:
        Encrypted data as bytes
    """
    return encrypt_data(text.encode(encoding), key)


def decrypt_string(encrypted_data: bytes, key: bytes, encoding: str = "utf-8") -> str:
    """
    Decrypt data to a string.

    Args:
        encrypted_data: Encrypted data as bytes
        key: Encryption key
        encoding: String encoding (default: utf-8)

    Returns:
        Decrypted string
    """
    return decrypt_data(encrypted_data, key).decode(encoding)
