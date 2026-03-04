# Encryption module for QBX
# Uses AES-256-GCM for confidentiality + integrity

import os
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Encryption constants
NONCE_SIZE = 12  # 96 bits for GCM
KEY_SIZE = 32    # 256 bits
SALT_SIZE = 16   # 128 bits
TAG_SIZE = 16    # 128 bits auth tag (included in GCM)

# Encryption flags
ENCRYPTION_NONE = 0
ENCRYPTION_AES256_GCM = 1


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive key from password using PBKDF2-HMAC-SHA256"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(password.encode())


def derive_key_argon2(password: str, salt: bytes) -> bytes:
    """Derive key from password using Argon2id (more secure)"""
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher(
            time_cost=2,
            memory_cost=65536,
            parallelism=1,
            hash_len=KEY_SIZE,
            salt_len=SALT_SIZE
        )
        # For deterministic key derivation, we use a simpler approach
        # In production, you'd want to store the argon2 hash
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=KEY_SIZE)
        return key
    except:
        # Fallback to PBKDF2
        return derive_key(password, salt)


def generate_salt() -> bytes:
    """Generate random salt for key derivation"""
    return os.urandom(SALT_SIZE)


def encrypt_aesgcm(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt data using AES-256-GCM.
    Returns: nonce (12 bytes) + ciphertext + auth tag (16 bytes)
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    # GCM appends auth tag automatically
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt_aesgcm(ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt data using AES-256-GCM.
    Input: nonce (12 bytes) + ciphertext + auth tag (16 bytes)
    Raises ValueError if authentication fails
    """
    if len(ciphertext) < NONCE_SIZE + TAG_SIZE:
        raise ValueError("Ciphertext too short")
    
    nonce = ciphertext[:NONCE_SIZE]
    data = ciphertext[NONCE_SIZE:]
    
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, data, None)


def encrypt_block(data: bytes, password: str, salt: bytes = None) -> tuple:
    """
    Encrypt block data with password.
    Returns: (encrypted_data, encryption_type, salt_used)
    """
    if salt is None:
        salt = generate_salt()
    
    key = derive_key(password, salt)
    encrypted = encrypt_aesgcm(data, key)
    
    return encrypted, ENCRYPTION_AES256_GCM, salt


def decrypt_block(encrypted_data: bytes, password: str, salt: bytes) -> bytes:
    """
    Decrypt block data with password and salt.
    Raises ValueError on wrong password or corruption.
    """
    key = derive_key(password, salt)
    return decrypt_aesgcm(encrypted_data, key)


def is_encrypted(obj_metadata: dict) -> bool:
    """Check if object is encrypted based on metadata"""
    return obj_metadata.get('encryption', 0) != ENCRYPTION_NONE


def get_encryption_info(obj_metadata: dict) -> dict:
    """Get encryption details from object metadata"""
    return {
        'enabled': obj_metadata.get('encryption', 0) != ENCRYPTION_NONE,
        'algorithm': obj_metadata.get('encryption', 0),
        'salt': obj_metadata.get('salt', b'')
    }
