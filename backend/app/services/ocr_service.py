"""
OCR Service for extracting text from generated images and videos.
Uses Google Cloud Vision API for text extraction.
"""
import io
import tempfile
import subprocess
from typing import Optional, List
from app.utils.logger import logger
from app.config import settings

# Try to import Google Cloud Vision
try:
    from google.cloud import vision
    VISION_AVAILABLE = True
except ImportError:
    vision = None
    VISION_AVAILABLE = False
    logger.warning("google-cloud-vision not installed. Install with: pip install google-cloud-vision")


class OCRService:
    """Service for extracting text from images and videos using Google Cloud Vision."""
    
    def __init__(self):
        """Initialize OCR service with Google Cloud Vision client."""
        self.client = None
        if VISION_AVAILABLE:
            try:
                # Try to initialize with default credentials or explicit credentials
                if settings.GOOGLE_CLOUD_VISION_CREDENTIALS:
                    import json
                    import os
                    
                    # Check if it's a file path or JSON content
                    creds = settings.GOOGLE_CLOUD_VISION_CREDENTIALS
                    if os.path.isfile(creds):
                        self.client = vision.ImageAnnotatorClient.from_service_account_file(creds)
                    else:
                        # Assume it's JSON content
                        creds_dict = json.loads(creds)
                        from google.oauth2 import service_account
                        credentials = service_account.Credentials.from_service_account_info(creds_dict)
                        self.client = vision.ImageAnnotatorClient(credentials=credentials)
                else:
                    # Use default credentials (ADC)
                    self.client = vision.ImageAnnotatorClient()
                logger.info("OCR Service initialized with Google Cloud Vision")
            except Exception as e:
                logger.error(f"Failed to initialize Google Cloud Vision client: {e}")
                self.client = None
    
    def extract_text_from_image(self, image_bytes: bytes) -> str:
        """
        Extract text from an image using Google Cloud Vision OCR.
        
        Args:
            image_bytes: Image data as bytes
            
        Returns:
            Extracted text from the image
        """
        if not self.client:
            logger.warning("OCR client not available, returning empty text")
            return ""
        
        try:
            logger.info(f"[OCR] Extracting text from image ({len(image_bytes)} bytes)...")
            
            image = vision.Image(content=image_bytes)
            
            # Use document_text_detection for better text accuracy
            response = self.client.document_text_detection(image=image)
            
            if response.error.message:
                logger.error(f"[OCR] Vision API error: {response.error.message}")
                return ""
            
            # Get full text from the response
            if response.full_text_annotation:
                extracted_text = response.full_text_annotation.text
                logger.info(f"[OCR] Extracted {len(extracted_text)} characters from image")
                return extracted_text.strip()
            
            # Fallback to text_annotations if full_text_annotation is empty
            if response.text_annotations:
                extracted_text = response.text_annotations[0].description
                logger.info(f"[OCR] Extracted {len(extracted_text)} characters from image (fallback)")
                return extracted_text.strip()
            
            logger.info("[OCR] No text found in image")
            return ""
            
        except Exception as e:
            logger.error(f"[OCR] Error extracting text from image: {e}")
            return ""
    
    def extract_text_from_video(self, video_bytes: bytes, max_frames: int = 3) -> str:
        """
        Extract text from a video by extracting key frames and running OCR.
        
        Args:
            video_bytes: Video data as bytes
            max_frames: Maximum number of frames to extract for OCR
            
        Returns:
            Combined extracted text from video frames
        """
        if not self.client:
            logger.warning("OCR client not available, returning empty text")
            return ""
        
        try:
            logger.info(f"[OCR] Extracting text from video ({len(video_bytes)} bytes)...")
            
            # Create temp file for video
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
                temp_video.write(video_bytes)
                temp_video_path = temp_video.name
            
            # Extract frames using ffmpeg
            frames = self._extract_video_frames(temp_video_path, max_frames)
            
            # Clean up temp video file
            import os
            try:
                os.unlink(temp_video_path)
            except:
                pass
            
            if not frames:
                logger.warning("[OCR] No frames extracted from video")
                return ""
            
            # Run OCR on each frame and combine results
            all_texts = []
            unique_texts = set()
            
            for i, frame_bytes in enumerate(frames):
                frame_text = self.extract_text_from_image(frame_bytes)
                if frame_text:
                    # Deduplicate text that appears in multiple frames
                    normalized = frame_text.lower().strip()
                    if normalized not in unique_texts:
                        unique_texts.add(normalized)
                        all_texts.append(frame_text)
            
            combined_text = "\n".join(all_texts)
            logger.info(f"[OCR] Extracted {len(combined_text)} characters from {len(frames)} video frames")
            return combined_text
            
        except Exception as e:
            logger.error(f"[OCR] Error extracting text from video: {e}")
            return ""
    
    def _extract_video_frames(self, video_path: str, max_frames: int = 3) -> List[bytes]:
        """
        Extract key frames from a video using ffmpeg.
        
        Args:
            video_path: Path to the video file
            max_frames: Maximum number of frames to extract
            
        Returns:
            List of frame image bytes (PNG format)
        """
        frames = []
        
        try:
            # Get video duration first
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            duration = float(result.stdout.strip()) if result.stdout.strip() else 5.0
            
            # Calculate timestamps for frame extraction (spread evenly)
            if duration <= 0:
                duration = 5.0
            
            # Extract frames at 25%, 50%, and 75% of the video
            timestamps = [duration * (i + 1) / (max_frames + 1) for i in range(max_frames)]
            
            for i, ts in enumerate(timestamps):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_frame:
                    temp_frame_path = temp_frame.name
                
                # Extract frame at timestamp
                extract_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(ts),
                    "-i", video_path,
                    "-vframes", "1",
                    "-f", "image2",
                    temp_frame_path
                ]
                
                subprocess.run(extract_cmd, capture_output=True, timeout=30)
                
                # Read frame bytes
                import os
                if os.path.exists(temp_frame_path) and os.path.getsize(temp_frame_path) > 0:
                    with open(temp_frame_path, "rb") as f:
                        frames.append(f.read())
                
                # Clean up
                try:
                    os.unlink(temp_frame_path)
                except:
                    pass
            
            logger.info(f"[OCR] Extracted {len(frames)} frames from video")
            return frames
            
        except Exception as e:
            logger.error(f"[OCR] Failed to extract video frames: {e}")
            return []
    
    def extract_text_sync(self, media_bytes: bytes, media_type: str) -> str:
        """
        Synchronous method to extract text from media (for Celery workers).
        
        Args:
            media_bytes: Media data as bytes
            media_type: "image" or "video"
            
        Returns:
            Extracted text
        """
        if media_type == "video":
            return self.extract_text_from_video(media_bytes)
        else:
            return self.extract_text_from_image(media_bytes)


# Singleton instance
_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Get singleton OCR service instance."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
