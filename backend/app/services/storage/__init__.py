"""
Storage factory - returns appropriate storage backend based on config
"""
from app.config import settings
from app.services.storage.base import StorageBackend
from app.services.storage.local_storage import LocalStorage
from app.services.storage.s3_storage import S3Storage
from app.services.storage.cloudinary_storage import CloudinaryStorage


def get_storage() -> StorageBackend:
    """Factory function to get storage backend based on config"""
    
    if settings.STORAGE_BACKEND == "s3":
        if not all([settings.S3_BUCKET, settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY]):
            raise ValueError(
                "S3 storage requires S3_BUCKET, S3_ACCESS_KEY, and S3_SECRET_KEY to be set"
            )
        
        return S3Storage(
            bucket_name=settings.S3_BUCKET,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
            endpoint_url=settings.S3_ENDPOINT_URL,
            region=settings.S3_REGION
        )
    elif settings.STORAGE_BACKEND == "cloudinary":
        if not all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET]):
            raise ValueError(
                "Cloudinary storage requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET to be set"
            )
        
        return CloudinaryStorage(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET
        )
    else:
        return LocalStorage(base_path=settings.LOCAL_STORAGE_PATH)

