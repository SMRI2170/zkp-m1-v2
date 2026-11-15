package org.smri.ridobserver.core
actual fun sha256(bytes: ByteArray): String = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).hex()
