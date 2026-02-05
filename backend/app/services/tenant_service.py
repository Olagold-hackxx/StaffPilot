"""
Tenant service - handles tenant operations
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID, uuid4
from slugify import slugify
from app.models.tenant import Tenant
from app.utils.errors import TenantNotFoundError
from app.utils.logger import logger


class TenantService:
    """Service for handling tenants"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_tenant(
        self,
        name: str,
        slug: Optional[str] = None,
        domain: Optional[str] = None,
        brand_voice: str = "professional",
        target_audience: Optional[str] = None,
        offerings: Optional[str] = None
    ) -> Tenant:
        """Create a new tenant and initialize default assistants"""
        if not slug:
            slug = slugify(name)
        
        # Ensure slug is unique
        existing = await self.get_tenant_by_slug(slug)
        if existing:
            slug = f"{slug}-{uuid4().hex[:8]}"
        
        tenant = Tenant(
            name=name,
            slug=slug,
            domain=domain,
            brand_voice=brand_voice,
            target_audience=target_audience,
            offerings=offerings
        )
        
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        
        # Initialize default assistants for the tenant
        from app.services.assistant_service import AssistantService
        assistant_service = AssistantService(self.db)
        await assistant_service.initialize_default_assistants(tenant.id)
        
        logger.info(f"Created tenant {tenant.id}: {tenant.name}")
        return tenant
    
    async def get_tenant(
        self,
        tenant_id: UUID
    ) -> Tenant:
        """Get tenant by ID"""
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise TenantNotFoundError(str(tenant_id))
        
        return tenant
    
    async def get_tenant_by_slug(
        self,
        slug: str
    ) -> Optional[Tenant]:
        """Get tenant by slug"""
        result = await self.db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()
    
    async def list_tenants(
        self,
        limit: int = 50,
        offset: int = 0,
        is_active: Optional[bool] = None
    ) -> tuple[List[Tenant], int]:
        """List tenants"""
        query = select(Tenant)
        
        if is_active is not None:
            query = query.where(Tenant.is_active == is_active)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()
        
        # Get tenants
        query = query.order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        tenants = result.scalars().all()
        
        return list(tenants), total
    
    async def update_tenant(
        self,
        tenant_id: UUID,
        **kwargs
    ) -> Tenant:
        """Update tenant"""
        tenant = await self.get_tenant(tenant_id)
        
        allowed_fields = [
            'name', 'domain', 'brand_voice', 'target_audience',
            'offerings', 'custom_config', 'is_active', 'is_onboarded',
            'website_url', 'brand_colors'  # Website URL for campaigns/ads
        ]
        
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                setattr(tenant, field, value)
        
        await self.db.commit()
        await self.db.refresh(tenant)
        
        logger.info(f"Updated tenant {tenant_id}")
        return tenant

