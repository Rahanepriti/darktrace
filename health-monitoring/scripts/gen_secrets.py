"""Print fresh secrets for your .env (never commit the output)."""
import secrets
import base64

print("HEALTH_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
print("HEALTH_API_TOKEN=" + secrets.token_urlsafe(32))
print("CRAWLER_WS_TOKEN=" + secrets.token_urlsafe(32))
print("POSTGRES_PASSWORD=" + secrets.token_hex(16))
print("REDIS_PASSWORD=" + secrets.token_hex(16))
