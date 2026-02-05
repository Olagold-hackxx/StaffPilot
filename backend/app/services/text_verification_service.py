"""
Text Verification Service for validating OCR-extracted text using Gemini AI.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
from app.utils.logger import logger
from app.config import settings


@dataclass
class VerificationResult:
    """Result of text verification."""
    is_valid: bool  # True if text passes verification
    has_text: bool  # True if any text was detected
    errors: list[str]  # List of detected errors
    corrections: str  # Suggested corrections to append to prompt
    confidence: float  # Confidence score (0-1)
    extracted_text: str  # The original extracted text


class TextVerificationService:
    """Service for verifying text extracted from generated content using Gemini."""
    
    def __init__(self):
        """Initialize with Gemini client."""
        self.client = None
        try:
            from google import genai
            api_key = settings.GOOGLE_API_KEY
            if api_key:
                self.client = genai.Client(api_key=api_key)
                logger.info("Text Verification Service initialized with Gemini")
            else:
                logger.warning("No GOOGLE_API_KEY found, text verification disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client for text verification: {e}")
    
    def verify_text(
        self,
        extracted_text: str,
        expected_context: str,
        language: str = "English",
        allowed_terms: Optional[list[str]] = None
    ) -> VerificationResult:
        """
        Verify extracted text against expected context using Gemini.
        
        Args:
            extracted_text: Text extracted from the image/video via OCR
            expected_context: The original prompt or expected text/context
            extracted_text: Text extracted from the image/video via OCR
            expected_context: The original prompt or expected text/context
            language: Expected language of the text
            allowed_terms: List of terms (e.g. brand names) that are valid regardless of dictionary spelling
            
        Returns:
            VerificationResult with validation status and corrections
        """
        # If no text was extracted, consider it valid (no text to verify)
        if not extracted_text or not extracted_text.strip():
            logger.info("[TextVerification] No text detected in content, skipping verification")
            return VerificationResult(
                is_valid=True,
                has_text=False,
                errors=[],
                corrections="",
                confidence=1.0,
                extracted_text=""
            )
        
        if not self.client:
            logger.warning("[TextVerification] Client not available, skipping verification")
            return VerificationResult(
                is_valid=True,
                has_text=True,
                errors=["Verification service unavailable"],
                corrections="",
                confidence=0.5,
                extracted_text=extracted_text
            )
        
        try:
            logger.info(f"[TextVerification] Verifying text: '{extracted_text[:100]}...'")
            
            prompt = f"""You are a text quality verification expert. Analyze the following OCR-extracted text from an AI-generated image or video.

OCR EXTRACTED TEXT:
"{extracted_text}"

ORIGINAL PROMPT/CONTEXT:
"{expected_context}"

EXPECTED LANGUAGE: {language}

ALLOW LIST (These terms are VALID business/product names - DO NOT flag them as spelling errors):
{", ".join(allowed_terms) if allowed_terms else "None provided"}

Your task:
1. Check if the text is in the correct language ({language})
2. Check for spelling errors
3. Check for garbled/unreadable text
4. Check if the text makes sense in context
5. Check for any unwanted characters or encoding issues

IMPORTANT: Be lenient - minor issues are acceptable. Only flag significant errors.

Respond in the following JSON format ONLY:
{{
    "is_valid": true/false,
    "errors": ["list of errors found, empty if valid"],
    "corrections": "If invalid, provide a corrected version of what the text SHOULD say. If valid, leave empty.",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
}}"""

            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            # Parse response
            response_text = ""
            if hasattr(response, 'text') and response.text:
                response_text = response.text
            elif hasattr(response, 'parts') and response.parts:
                response_text = " ".join([p.text for p in response.parts if hasattr(p, 'text')])
            
            # Extract JSON from response
            import json
            import re
            
            # Try to extract JSON from the response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result_dict = json.loads(json_match.group())
                
                is_valid = result_dict.get("is_valid", True)
                errors = result_dict.get("errors", [])
                corrections = result_dict.get("corrections", "")
                confidence = float(result_dict.get("confidence", 0.8))
                
                if not is_valid:
                    logger.info(f"[TextVerification] FAIL - Errors: {errors}")
                    # Build correction prompt addition
                    if corrections:
                        correction_prompt = f"\n\nIMPORTANT TEXT CORRECTION: The text in this content MUST read exactly as: '{corrections}'. Do NOT include spelling errors or garbled text. Ensure all text is clear, correct, and in {language}."
                    else:
                        correction_prompt = f"\n\nIMPORTANT: Ensure all text in this content is spelled correctly, is clear and readable, and is in {language}. Avoid any garbled or incorrect text."
                else:
                    correction_prompt = ""
                    logger.info(f"[TextVerification] PASS - Confidence: {confidence}")
                
                return VerificationResult(
                    is_valid=is_valid,
                    has_text=True,
                    errors=errors if isinstance(errors, list) else [str(errors)],
                    corrections=correction_prompt,
                    confidence=confidence,
                    extracted_text=extracted_text
                )
            else:
                logger.warning("[TextVerification] Could not parse Gemini response as JSON")
                return VerificationResult(
                    is_valid=True,
                    has_text=True,
                    errors=["Could not parse verification response"],
                    corrections="",
                    confidence=0.5,
                    extracted_text=extracted_text
                )
                
        except Exception as e:
            logger.error(f"[TextVerification] Error during verification: {e}")
            # On error, assume valid to avoid blocking generation
            return VerificationResult(
                is_valid=True,
                has_text=True,
                errors=[f"Verification error: {str(e)}"],
                corrections="",
                confidence=0.5,
                extracted_text=extracted_text
            )
    
    def verify_text_sync(
        self,
        extracted_text: str,
        expected_context: str,
        language: str = "English",
        allowed_terms: Optional[list[str]] = None
    ) -> VerificationResult:
        """
        Synchronous version for Celery workers.
        The main verify_text method is already synchronous using the sync Gemini client.
        """
        """
        return self.verify_text(extracted_text, expected_context, language, allowed_terms)


# Singleton instance
_verification_service: Optional[TextVerificationService] = None


def get_text_verification_service() -> TextVerificationService:
    """Get singleton text verification service instance."""
    global _verification_service
    if _verification_service is None:
        _verification_service = TextVerificationService()
    return _verification_service


def verify_and_correct_content(
    media_bytes: bytes,
    media_type: str,
    original_prompt: str,
    max_retries: int = 2,
    allowed_terms: Optional[list[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to verify content and return correction status.
    
    Args:
        media_bytes: The generated media content
        media_type: "image" or "video"
        original_prompt: The prompt used to generate the content
        max_retries: Maximum regeneration attempts
        
    Returns:
        Dict with keys:
            - needs_regeneration: bool
            - corrected_prompt: str (if regeneration needed)
            - verification_result: VerificationResult
    """
    from app.services.ocr_service import get_ocr_service
    
    if not settings.OCR_ENABLED:
        return {
            "needs_regeneration": False,
            "corrected_prompt": original_prompt,
            "verification_result": None
        }
    
    ocr_service = get_ocr_service()
    verification_service = get_text_verification_service()
    
    # Extract text from media
    extracted_text = ocr_service.extract_text_sync(media_bytes, media_type)
    
    # Verify the extracted text
    result = verification_service.verify_text_sync(
        extracted_text=extracted_text,
        expected_context=original_prompt,
        allowed_terms=allowed_terms
    )
    
    if result.is_valid or not result.has_text:
        return {
            "needs_regeneration": False,
            "corrected_prompt": original_prompt,
            "verification_result": result
        }
    else:
        # Build corrected prompt
        corrected_prompt = original_prompt + result.corrections
        return {
            "needs_regeneration": True,
            "corrected_prompt": corrected_prompt,
            "verification_result": result
        }
