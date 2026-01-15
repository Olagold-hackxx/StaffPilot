"""
Scheduled Posts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.models.user import User
from app.models.tenant import Tenant
from app.models.content import ScheduledPost
from app.models.assistant import Assistant
from app.utils.logger import logger

router = APIRouter(prefix="/scheduled-posts", tags=["scheduled-posts"])


class ScheduleConfig(BaseModel):
    """Schedule configuration based on schedule type"""
    hour: int = Field(default=9, ge=0, le=23, description="Hour of day (0-23)")
    minute: int = Field(default=0, ge=0, le=59, description="Minute of hour (0-59)")
    days_of_week: Optional[List[int]] = Field(default=None, description="Days of week (0=Monday, 6=Sunday) for weekly schedules")
    days_of_month: Optional[List[int]] = Field(default=None, description="Days of month (1-31) for monthly schedules")


class ScheduledPostCreate(BaseModel):
    name: str = Field(..., description="User-friendly name for the schedule")
    assistant_id: str = Field(..., description="Assistant ID")
    capability_id: Optional[str] = Field(None, description="Capability ID")
    schedule_type: str = Field(..., description="Schedule type: one_time, daily, weekly, monthly")
    schedule_config: ScheduleConfig = Field(..., description="Schedule configuration")
    request: str = Field(..., description="Content request/prompt")
    platforms: List[str] = Field(default=[], description="List of platforms to post to")
    include_images: bool = Field(default=False, description="Include images in content")
    include_video: bool = Field(default=False, description="Include video in content")
    requires_approval: bool = Field(default=False, description="If true, content requires manual approval before publishing")
    start_date: str = Field(..., description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format, optional)")


class ScheduledPostUpdate(BaseModel):
    name: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_config: Optional[ScheduleConfig] = None
    request: Optional[str] = None
    platforms: Optional[List[str]] = None
    include_images: Optional[bool] = None
    include_video: Optional[bool] = None
    requires_approval: Optional[bool] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduledPostResponse(BaseModel):
    id: str
    name: str
    assistant_id: str
    capability_id: Optional[str]
    schedule_type: str
    schedule_config: Dict[str, Any]
    request: str
    platforms: List[str]
    include_images: bool
    include_video: bool
    requires_approval: bool
    start_date: str
    end_date: Optional[str]
    next_run_at: str
    last_run_at: Optional[str]
    is_active: bool
    status: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True


def _calculate_next_run(schedule_type: str, schedule_config: Dict[str, Any], start_date: datetime) -> datetime:
    """Calculate next run time from start date"""
    if schedule_type == "one_time":
        return start_date
    
    hour = schedule_config.get("hour", 9)
    minute = schedule_config.get("minute", 0)
    
    # For recurring schedules, use the start_date as base
    next_run = start_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    if schedule_type == "daily":
        # If time has passed today, schedule for tomorrow
        if next_run <= datetime.now(timezone.utc):
            next_run += timedelta(days=1)
    elif schedule_type == "weekly":
        days_of_week = schedule_config.get("days_of_week", [0])
        current_weekday = start_date.weekday()
        # Find next matching day
        for day in sorted(days_of_week):
            if day > current_weekday:
                days_ahead = day - current_weekday
                next_run += timedelta(days=days_ahead)
                break
        else:
            # Use first day of next week
            first_day = min(days_of_week)
            days_ahead = (7 - current_weekday) + first_day
            next_run += timedelta(days=days_ahead)
    elif schedule_type == "monthly":
        days_of_month = schedule_config.get("days_of_month", [1])
        current_day = start_date.day
        # Find next matching day
        for day in sorted(days_of_month):
            if day > current_day:
                try:
                    next_run = start_date.replace(day=day)
                    break
                except ValueError:
                    continue
        else:
            # Use first day of next month
            first_day = min(days_of_month)
            if start_date.month == 12:
                next_month = start_date.replace(year=start_date.year + 1, month=1, day=1)
            else:
                next_month = start_date.replace(month=start_date.month + 1, day=1)
            try:
                next_run = next_month.replace(day=first_day)
            except ValueError:
                from calendar import monthrange
                last_day = monthrange(next_month.year, next_month.month)[1]
                next_run = next_month.replace(day=min(first_day, last_day))
    
    return next_run


@router.post("", response_model=ScheduledPostResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_post(
    post_data: ScheduledPostCreate,
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Create a new scheduled post"""
    try:
        # Verify assistant belongs to tenant
        assistant_id = UUID(post_data.assistant_id)
        result = await db.execute(
            select(Assistant).where(
                Assistant.id == assistant_id,
                Assistant.tenant_id == current_tenant.id
            )
        )
        assistant = result.scalar_one_or_none()
        
        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assistant not found"
            )
        
        # Parse dates
        start_date = datetime.fromisoformat(post_data.start_date.replace('Z', '+00:00'))
        end_date = None
        if post_data.end_date:
            end_date = datetime.fromisoformat(post_data.end_date.replace('Z', '+00:00'))
        
        # Calculate next run time
        schedule_config_dict = post_data.schedule_config.dict()
        next_run_at = _calculate_next_run(post_data.schedule_type, schedule_config_dict, start_date)
        
        # Create scheduled post
        scheduled_post = ScheduledPost(
            tenant_id=current_tenant.id,
            assistant_id=assistant_id,
            capability_id=UUID(post_data.capability_id) if post_data.capability_id else None,
            name=post_data.name,
            schedule_type=post_data.schedule_type,
            schedule_config=schedule_config_dict,
            request=post_data.request,
            platforms=post_data.platforms,
            include_images=post_data.include_images,
            include_video=post_data.include_video,
            requires_approval=post_data.requires_approval,
            start_date=start_date,
            end_date=end_date,
            next_run_at=next_run_at,
            is_active=True,
            status="active",
            created_by=current_user.id
        )
        
        db.add(scheduled_post)
        await db.commit()
        await db.refresh(scheduled_post)
        
        logger.info(f"Created scheduled post {scheduled_post.id} for tenant {current_tenant.id}")
        
        return ScheduledPostResponse(
            id=str(scheduled_post.id),
            name=scheduled_post.name,
            assistant_id=str(scheduled_post.assistant_id),
            capability_id=str(scheduled_post.capability_id) if scheduled_post.capability_id else None,
            schedule_type=scheduled_post.schedule_type,
            schedule_config=scheduled_post.schedule_config,
            request=scheduled_post.request,
            platforms=scheduled_post.platforms or [],
            include_images=scheduled_post.include_images,
            include_video=scheduled_post.include_video,
            requires_approval=scheduled_post.requires_approval,
            start_date=scheduled_post.start_date.isoformat(),
            end_date=scheduled_post.end_date.isoformat() if scheduled_post.end_date else None,
            next_run_at=scheduled_post.next_run_at.isoformat(),
            last_run_at=scheduled_post.last_run_at.isoformat() if scheduled_post.last_run_at else None,
            is_active=scheduled_post.is_active,
            status=scheduled_post.status,
            total_runs=scheduled_post.total_runs,
            successful_runs=scheduled_post.successful_runs,
            failed_runs=scheduled_post.failed_runs,
            created_at=scheduled_post.created_at.isoformat(),
            updated_at=scheduled_post.updated_at.isoformat() if scheduled_post.updated_at else None
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error creating scheduled post: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scheduled post: {str(e)}"
        )


@router.get("", response_model=Dict[str, Any])
async def list_scheduled_posts(
    assistant_id: Optional[UUID] = None,
    is_active: Optional[bool] = None,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List scheduled posts for the current tenant"""
    try:
        conditions = [ScheduledPost.tenant_id == current_tenant.id]
        
        if assistant_id:
            conditions.append(ScheduledPost.assistant_id == assistant_id)
        
        if is_active is not None:
            conditions.append(ScheduledPost.is_active == is_active)
        
        result = await db.execute(
            select(ScheduledPost).where(and_(*conditions)).order_by(ScheduledPost.next_run_at)
        )
        scheduled_posts = result.scalars().all()
        
        return {
            "scheduled_posts": [
                {
                    "id": str(sp.id),
                    "name": sp.name,
                    "assistant_id": str(sp.assistant_id),
                    "capability_id": str(sp.capability_id) if sp.capability_id else None,
                    "schedule_type": sp.schedule_type,
                    "schedule_config": sp.schedule_config,
                    "request": sp.request,
                    "platforms": sp.platforms or [],
                    "include_images": sp.include_images,
                    "include_video": sp.include_video,
                    "requires_approval": sp.requires_approval,
                    "start_date": sp.start_date.isoformat(),
                    "end_date": sp.end_date.isoformat() if sp.end_date else None,
                    "next_run_at": sp.next_run_at.isoformat(),
                    "last_run_at": sp.last_run_at.isoformat() if sp.last_run_at else None,
                    "is_active": sp.is_active,
                    "status": sp.status,
                    "total_runs": sp.total_runs,
                    "successful_runs": sp.successful_runs,
                    "failed_runs": sp.failed_runs,
                    "created_at": sp.created_at.isoformat(),
                    "updated_at": sp.updated_at.isoformat() if sp.updated_at else None
                }
                for sp in scheduled_posts
            ],
            "total": len(scheduled_posts)
        }
    
    except Exception as e:
        logger.error(f"Error listing scheduled posts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list scheduled posts"
        )


# ============================================
# Content Approval Endpoints
# ============================================

@router.get("/pending-content", response_model=Dict[str, Any])
async def list_pending_content(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List all content items pending approval for the current tenant"""
    try:
        from app.models.content import ContentItem
        
        result = await db.execute(
            select(ContentItem).where(
                ContentItem.tenant_id == current_tenant.id,
                ContentItem.publish_status == "pending_approval"
            ).order_by(ContentItem.created_at.desc())
        )
        pending_items = result.scalars().all()
        
        return {
            "pending_content": [
                {
                    "id": str(item.id),
                    "platform": item.platform,
                    "content": item.content,
                    "title": item.title,
                    "images": item.images or [],
                    "videos": item.videos or [],
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "execution_id": str(item.execution_id) if item.execution_id else None
                }
                for item in pending_items
            ],
            "total": len(pending_items)
        }
    
    except Exception as e:
        logger.error(f"Error listing pending content: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list pending content"
        )


@router.post("/content/{content_id}/approve")
async def approve_content(
    content_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Approve and publish a pending content item"""
    try:
        from app.models.content import ContentItem
        
        result = await db.execute(
            select(ContentItem).where(
                ContentItem.id == content_id,
                ContentItem.tenant_id == current_tenant.id
            )
        )
        content_item = result.scalar_one_or_none()
        
        if not content_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
        
        if content_item.publish_status != "pending_approval":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Content is not pending (status: {content_item.publish_status})")
        
        content_item.publish_status = "approved"
        await db.commit()
        
        logger.info(f"Approved content {content_id}")
        return {"status": "approved", "message": "Content approved and queued for publishing"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Failed to approve content")


@router.post("/content/{content_id}/reject")
async def reject_content(
    content_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Reject a pending content item"""
    try:
        from app.models.content import ContentItem
        
        result = await db.execute(
            select(ContentItem).where(
                ContentItem.id == content_id,
                ContentItem.tenant_id == current_tenant.id
            )
        )
        content_item = result.scalar_one_or_none()
        
        if not content_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
        
        if content_item.publish_status != "pending_approval":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail=f"Content is not pending (status: {content_item.publish_status})")
        
        content_item.publish_status = "rejected"
        await db.commit()
        
        logger.info(f"Rejected content {content_id}")
        return {"status": "rejected"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Failed to reject content")


@router.get("/{scheduled_post_id}", response_model=ScheduledPostResponse)
async def get_scheduled_post(
    scheduled_post_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific scheduled post"""
    try:
        result = await db.execute(
            select(ScheduledPost).where(
                ScheduledPost.id == scheduled_post_id,
                ScheduledPost.tenant_id == current_tenant.id
            )
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled post not found"
            )
        
        return ScheduledPostResponse(
            id=str(scheduled_post.id),
            name=scheduled_post.name,
            assistant_id=str(scheduled_post.assistant_id),
            capability_id=str(scheduled_post.capability_id) if scheduled_post.capability_id else None,
            schedule_type=scheduled_post.schedule_type,
            schedule_config=scheduled_post.schedule_config,
            request=scheduled_post.request,
            platforms=scheduled_post.platforms or [],
            include_images=scheduled_post.include_images,
            include_video=scheduled_post.include_video,
            requires_approval=scheduled_post.requires_approval,
            start_date=scheduled_post.start_date.isoformat(),
            end_date=scheduled_post.end_date.isoformat() if scheduled_post.end_date else None,
            next_run_at=scheduled_post.next_run_at.isoformat(),
            last_run_at=scheduled_post.last_run_at.isoformat() if scheduled_post.last_run_at else None,
            is_active=scheduled_post.is_active,
            status=scheduled_post.status,
            total_runs=scheduled_post.total_runs,
            successful_runs=scheduled_post.successful_runs,
            failed_runs=scheduled_post.failed_runs,
            created_at=scheduled_post.created_at.isoformat(),
            updated_at=scheduled_post.updated_at.isoformat() if scheduled_post.updated_at else None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scheduled post: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scheduled post"
        )


@router.put("/{scheduled_post_id}", response_model=ScheduledPostResponse)
async def update_scheduled_post(
    scheduled_post_id: UUID,
    post_data: ScheduledPostUpdate,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Update a scheduled post"""
    try:
        result = await db.execute(
            select(ScheduledPost).where(
                ScheduledPost.id == scheduled_post_id,
                ScheduledPost.tenant_id == current_tenant.id
            )
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled post not found"
            )
        
        # Update fields
        if post_data.name is not None:
            scheduled_post.name = post_data.name
        if post_data.schedule_type is not None:
            scheduled_post.schedule_type = post_data.schedule_type
        if post_data.schedule_config is not None:
            scheduled_post.schedule_config = post_data.schedule_config.dict()
        if post_data.request is not None:
            scheduled_post.request = post_data.request
        if post_data.platforms is not None:
            scheduled_post.platforms = post_data.platforms
        if post_data.include_images is not None:
            scheduled_post.include_images = post_data.include_images
        if post_data.include_video is not None:
            scheduled_post.include_video = post_data.include_video
        if post_data.requires_approval is not None:
            scheduled_post.requires_approval = post_data.requires_approval
        if post_data.start_date is not None:
            scheduled_post.start_date = datetime.fromisoformat(post_data.start_date.replace('Z', '+00:00'))
        if post_data.end_date is not None:
            if post_data.end_date:
                scheduled_post.end_date = datetime.fromisoformat(post_data.end_date.replace('Z', '+00:00'))
            else:
                scheduled_post.end_date = None
        if post_data.is_active is not None:
            scheduled_post.is_active = post_data.is_active
            if not post_data.is_active:
                scheduled_post.status = "paused"
            elif scheduled_post.status == "paused":
                scheduled_post.status = "active"
        
        # Recalculate next_run_at if schedule changed
        if post_data.schedule_type is not None or post_data.schedule_config is not None or post_data.start_date is not None:
            next_run_at = _calculate_next_run(
                scheduled_post.schedule_type,
                scheduled_post.schedule_config,
                scheduled_post.start_date
            )
            scheduled_post.next_run_at = next_run_at
        
        await db.commit()
        await db.refresh(scheduled_post)
        
        logger.info(f"Updated scheduled post {scheduled_post.id}")
        
        return ScheduledPostResponse(
            id=str(scheduled_post.id),
            name=scheduled_post.name,
            assistant_id=str(scheduled_post.assistant_id),
            capability_id=str(scheduled_post.capability_id) if scheduled_post.capability_id else None,
            schedule_type=scheduled_post.schedule_type,
            schedule_config=scheduled_post.schedule_config,
            request=scheduled_post.request,
            platforms=scheduled_post.platforms or [],
            include_images=scheduled_post.include_images,
            include_video=scheduled_post.include_video,
            requires_approval=scheduled_post.requires_approval,
            start_date=scheduled_post.start_date.isoformat(),
            end_date=scheduled_post.end_date.isoformat() if scheduled_post.end_date else None,
            next_run_at=scheduled_post.next_run_at.isoformat(),
            last_run_at=scheduled_post.last_run_at.isoformat() if scheduled_post.last_run_at else None,
            is_active=scheduled_post.is_active,
            status=scheduled_post.status,
            total_runs=scheduled_post.total_runs,
            successful_runs=scheduled_post.successful_runs,
            failed_runs=scheduled_post.failed_runs,
            created_at=scheduled_post.created_at.isoformat(),
            updated_at=scheduled_post.updated_at.isoformat() if scheduled_post.updated_at else None
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error updating scheduled post: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update scheduled post"
        )


@router.delete("/{scheduled_post_id}")
async def delete_scheduled_post(
    scheduled_post_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Delete a scheduled post"""
    try:
        result = await db.execute(
            select(ScheduledPost).where(
                ScheduledPost.id == scheduled_post_id,
                ScheduledPost.tenant_id == current_tenant.id
            )
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled post not found"
            )
        
        await db.delete(scheduled_post)
        await db.commit()
        
        logger.info(f"Deleted scheduled post {scheduled_post_id}")
        
        return {"status": "deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting scheduled post: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete scheduled post"
        )



