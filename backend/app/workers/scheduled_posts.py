"""
Scheduled Posts Worker - Celery tasks for periodic content posting
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from uuid import UUID
from celery.schedules import crontab

from app.workers import celery_app
from app.utils.logger import logger
from app.workers.content_creation import execute_content_creation


@celery_app.task(name="scheduled_posts.check_scheduled", bind=True, max_retries=3)
def check_scheduled_posts(self) -> Dict[str, Any]:
    """
    Periodic task to check for scheduled posts that need to be published.
    This task only finds due posts and triggers separate execution tasks.
    Called by Celery Beat on a regular interval (every 2 minutes).
    """
    try:
        from app.db.session import create_worker_session_factory
        from sqlalchemy import select, and_
        from app.models.content import ScheduledPost
        
        SessionFactory = create_worker_session_factory()
        db = SessionFactory()
        try:
            now = datetime.now(timezone.utc)
            
            # Find all active scheduled posts that are due for publishing
            # Using sync session - no await needed
            result = db.execute(
                select(ScheduledPost).where(
                    and_(
                        ScheduledPost.is_active == True,
                        ScheduledPost.status == "active",
                        ScheduledPost.next_run_at <= now,
                        (ScheduledPost.end_date.is_(None)) | (ScheduledPost.end_date >= now)
                    )
                )
            )
            scheduled_posts = result.scalars().all()
            
            if len(scheduled_posts) == 0:
                logger.debug("No scheduled posts ready to execute")
                return {
                    "success": True,
                    "triggered_count": 0,
                    "total_found": 0
                }
            
            logger.info(f"Found {len(scheduled_posts)} scheduled posts ready to execute")
            
            triggered_count = 0
            for scheduled_post in scheduled_posts:
                try:
                    # Validate that the scheduled post has required data
                    if not scheduled_post.platforms or len(scheduled_post.platforms) == 0:
                        logger.warning(f"No platforms configured for scheduled post {scheduled_post.id}")
                        scheduled_post.status = "failed"
                        scheduled_post.is_active = False
                        db.commit()  # Sync commit - no await
                        continue
                    
                    # Trigger the execution task for this scheduled post
                    execute_scheduled_post.delay(str(scheduled_post.id))
                    triggered_count += 1
                    logger.info(f"Triggered execution for scheduled post {scheduled_post.id} ({scheduled_post.name})")
                    
                except Exception as e:
                    logger.error(f"Error triggering scheduled post {scheduled_post.id}: {str(e)}", exc_info=True)
            
            logger.info(f"Processed {triggered_count} scheduled posts")
            return {
                "success": True,
                "triggered_count": triggered_count,
                "total_found": len(scheduled_posts)
            }
            
        finally:
            db.close()  # Sync close - no await
    
    except Exception as e:
        logger.error(f"Error checking scheduled posts: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=2**self.request.retries)


@celery_app.task(name="scheduled_posts.execute_scheduled", bind=True, max_retries=3)
def execute_scheduled_post(self, scheduled_post_id: str) -> Dict[str, Any]:
    """
    Execute a single scheduled post.
    This task handles the actual execution, including:
    - Creating execution record
    - Triggering content creation
    - Updating scheduled post status and next run time
    """
    try:
        from app.db.session import create_worker_session_factory
        from sqlalchemy import select
        from app.models.content import ScheduledPost
        from app.models.agent_execution import AgentExecution
        
        # Create a new session factory for this worker task (sync)
        SessionFactory = create_worker_session_factory()
        db = SessionFactory()
        try:
            now = datetime.now(timezone.utc)
            
            # Get the scheduled post (sync)
            result = db.execute(
                select(ScheduledPost).where(ScheduledPost.id == UUID(scheduled_post_id))
            )
            scheduled_post = result.scalar_one_or_none()
            
            if not scheduled_post:
                logger.error(f"Scheduled post {scheduled_post_id} not found")
                return {"success": False, "error": "Scheduled post not found"}
            
            if not scheduled_post.is_active or scheduled_post.status != "active":
                logger.warning(f"Scheduled post {scheduled_post_id} is not active")
                return {"success": False, "error": "Scheduled post is not active"}
            
            # Validate platforms
            if not scheduled_post.platforms or len(scheduled_post.platforms) == 0:
                logger.warning(f"No platforms configured for scheduled post {scheduled_post_id}")
                scheduled_post.status = "failed"
                scheduled_post.is_active = False
                db.commit()  # Sync commit
                return {"success": False, "error": "No platforms configured"}
            
            # Create execution record (sync)
            execution = AgentExecution(
                tenant_id=scheduled_post.tenant_id,
                assistant_id=scheduled_post.assistant_id,
                capability_id=scheduled_post.capability_id,
                request_type="create_content",
                request_data={
                    "request": scheduled_post.request,
                    "platforms": scheduled_post.platforms or [],
                    "include_images": scheduled_post.include_images,
                    "include_video": scheduled_post.include_video,
                },
                status="queued",
                initiated_by=scheduled_post.created_by
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            
            logger.info(f"Created agent execution {execution.id} for scheduled post {scheduled_post_id}")
            
            # Prepare request data
            request_data = {
                "request": scheduled_post.request,
                "platforms": scheduled_post.platforms or [],
                "include_images": scheduled_post.include_images,
                "include_video": scheduled_post.include_video,
                "requires_approval": scheduled_post.requires_approval,  # Pass approval flag
            }
            
            # Queue the content creation task
            execute_content_creation.delay(
                execution_id=str(execution.id),
                tenant_id=str(scheduled_post.tenant_id),
                assistant_id=str(scheduled_post.assistant_id),
                request_data=request_data
            )
            
            # Update scheduled post tracking
            scheduled_post.last_run_at = now
            scheduled_post.total_runs += 1
            scheduled_post.successful_runs += 1
            
            # Calculate next run time based on schedule type
            next_run = _calculate_next_run(
                scheduled_post.schedule_type,
                scheduled_post.schedule_config,
                now
            )
            
            if next_run:
                scheduled_post.next_run_at = next_run
                
                # Check if we've reached the end date
                if scheduled_post.end_date and next_run > scheduled_post.end_date:
                    scheduled_post.status = "completed"
                    scheduled_post.is_active = False
                    logger.info(f"Scheduled post {scheduled_post_id} has reached its end date")
            else:
                # One-time schedule completed
                scheduled_post.status = "completed"
                scheduled_post.is_active = False
                logger.info(f"One-time scheduled post {scheduled_post_id} completed")
            
            db.commit()  # Sync commit
            
            return {
                "success": True,
                "scheduled_post_id": scheduled_post_id,
                "execution_id": str(execution.id),
                "next_run_at": next_run.isoformat() if next_run else None
            }
            
        finally:
            db.close()  # Sync close
    
    except Exception as e:
        logger.error(f"Error executing scheduled post {scheduled_post_id}: {str(e)}", exc_info=True)
        
        # Update failure count (sync)
        try:
            from app.db.session import create_worker_session_factory
            from sqlalchemy import select
            from app.models.content import ScheduledPost
            
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            try:
                result = db.execute(
                    select(ScheduledPost).where(ScheduledPost.id == UUID(scheduled_post_id))
                )
                scheduled_post = result.scalar_one_or_none()
                
                if scheduled_post:
                    scheduled_post.failed_runs += 1
                    scheduled_post.total_runs += 1
                    
                    # If too many failures, mark as failed
                    if scheduled_post.failed_runs >= 5:
                        scheduled_post.status = "failed"
                        scheduled_post.is_active = False
                        logger.error(f"Scheduled post {scheduled_post_id} marked as failed after 5 failures")
                    
                    db.commit()  # Sync commit
            finally:
                db.close()  # Sync close
        except Exception as update_error:
            logger.error(f"Failed to update failure count: {str(update_error)}")
        
        raise self.retry(exc=e, countdown=2**self.request.retries)


def _calculate_next_run(schedule_type: str, schedule_config: Dict[str, Any], current_time: datetime) -> Optional[datetime]:
    """
    Calculate the next run time based on schedule type and configuration
    
    Args:
        schedule_type: one_time, daily, weekly, monthly
        schedule_config: Configuration dict with schedule-specific settings
        current_time: Current datetime
    
    Returns:
        Next run datetime or None if schedule is complete
    """
    if schedule_type == "one_time":
        return None  # One-time schedules don't repeat
    
    elif schedule_type == "daily":
        # Daily schedule: run at a specific time each day
        hour = schedule_config.get("hour", 9)
        minute = schedule_config.get("minute", 0)
        
        # Calculate next run (tomorrow at specified time)
        next_run = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= current_time:
            # If time has passed today, schedule for tomorrow
            next_run += timedelta(days=1)
        
        return next_run
    
    elif schedule_type == "weekly":
        # Weekly schedule: run on specific day(s) of week at specific time
        days_of_week = schedule_config.get("days_of_week", [0])  # 0=Monday, 6=Sunday
        hour = schedule_config.get("hour", 9)
        minute = schedule_config.get("minute", 0)
        
        # Find next matching day
        current_weekday = current_time.weekday()
        next_run = None
        
        # Check remaining days this week
        for day in sorted(days_of_week):
            if day > current_weekday:
                next_run = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                days_ahead = day - current_weekday
                next_run += timedelta(days=days_ahead)
                break
        
        # If no day found this week, use first day of next week
        if next_run is None:
            first_day = min(days_of_week)
            next_run = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = (7 - current_weekday) + first_day
            next_run += timedelta(days=days_ahead)
        
        return next_run
    
    elif schedule_type == "monthly":
        # Monthly schedule: run on specific day(s) of month at specific time
        days_of_month = schedule_config.get("days_of_month", [1])  # List of day numbers (1-31)
        hour = schedule_config.get("hour", 9)
        minute = schedule_config.get("minute", 0)
        
        # Find next matching day
        current_day = current_time.day
        next_run = None
        
        # Check remaining days this month
        for day in sorted(days_of_month):
            if day > current_day:
                try:
                    next_run = current_time.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    break
                except ValueError:
                    # Invalid day for this month (e.g., Feb 30), skip
                    continue
        
        # If no day found this month, use first day of next month
        if next_run is None:
            first_day = min(days_of_month)
            # Move to next month
            if current_time.month == 12:
                next_month = current_time.replace(year=current_time.year + 1, month=1, day=1, hour=hour, minute=minute, second=0, microsecond=0)
            else:
                next_month = current_time.replace(month=current_time.month + 1, day=1, hour=hour, minute=minute, second=0, microsecond=0)
            
            # Try to set the day
            try:
                next_run = next_month.replace(day=first_day)
            except ValueError:
                # If day doesn't exist in next month (e.g., Feb 30), use last day of month
                from calendar import monthrange
                last_day = monthrange(next_month.year, next_month.month)[1]
                next_run = next_month.replace(day=min(first_day, last_day))
        
        return next_run
    
    else:
        logger.warning(f"Unknown schedule type: {schedule_type}")
        return None

