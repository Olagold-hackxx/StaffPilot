"""
Style Extraction Service

Analyzes brand assets to extract a detailed style prompt for better
brand consistency in AI-generated content.
"""
from typing import List, Optional, Dict
from app.utils.logger import logger


def extract_style_prompt_sync(
    reference_images: List[bytes],
    brand_colors: Optional[List[str]] = None,
    company_name: Optional[str] = None
) -> str:
    """
    Analyze brand assets and extract a detailed style prompt.
    
    This is a two-step approach:
    1. Send reference images to AI for analysis
    2. Get back a detailed style prompt describing how to replicate the brand style
    
    Args:
        reference_images: List of image bytes (logo, brand assets, etc.)
        brand_colors: Optional list of hex color codes
        company_name: Optional company name for branding context
    
    Returns:
        A detailed style prompt string for use in image/video generation
    """
    if not reference_images:
        logger.warning("No reference images provided for style extraction")
        return ""
    
    try:
        from app.services.llm.factory import create_llm_service
        from google.genai import types
        
        llm_service = create_llm_service()
        
        # Build the analysis prompt
        analysis_prompt = _build_style_analysis_prompt(brand_colors, company_name)
        
        # Build contents with images first, then the analysis prompt
        contents = []
        
        for idx, img_bytes in enumerate(reference_images[:5]):  # Max 5 images for better context
            # Detect mime type
            mime_type = "image/jpeg"
            if img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = "image/png"
            elif img_bytes[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            
            contents.append(types.Part.from_bytes(
                data=img_bytes,
                mime_type=mime_type
            ))
            logger.info(f"Added reference image {idx+1} for style extraction ({len(img_bytes)} bytes)")
        
        # Add the analysis prompt
        contents.append(analysis_prompt)
        
        # Call Gemini for analysis
        response = llm_service.genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents
        )
        
        # Extract text from response
        style_prompt = ""
        if hasattr(response, 'text') and response.text:
            style_prompt = response.text.strip()
        elif hasattr(response, 'parts') and response.parts:
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    style_prompt += part.text
        
        if style_prompt:
            logger.info(f"Extracted style prompt ({len(style_prompt)} chars)")
            return style_prompt
        else:
            logger.warning("Style extraction returned empty response")
            return _build_fallback_style_prompt(brand_colors)
            
    except Exception as e:
        logger.error(f"Style extraction failed: {e}")
        return _build_fallback_style_prompt(brand_colors)


def _build_style_analysis_prompt(
    brand_colors: Optional[List[str]] = None,
    company_name: Optional[str] = None
) -> str:
    """Build the prompt for style analysis."""
    
    colors_context = ""
    if brand_colors:
        colors_str = ", ".join(brand_colors)
        colors_context = f"\n\nThe brand's official colors are: {colors_str}"
    
    company_context = ""
    if company_name:
        company_context = f" for {company_name}"
    
    return f"""Analyze these brand reference images{company_context} and create a detailed style guide prompt.

Your task is to describe the visual style in a way that can be used as instructions for generating NEW images that match this exact brand identity.

Focus on:

1. **LOGO TREATMENT**: Describe the logo exactly - its shape, colors, typography, and style. How should it appear in generated content? Where should it be placed?

2. **COLOR PALETTE**: Identify the exact colors used (describe as precisely as possible). Which is primary? Secondary? Accent?{colors_context}

3. **VISUAL STYLE**: Is it modern, classic, minimalist, bold, playful, professional? What defines the aesthetic?

4. **TYPOGRAPHY & FONTS** (CRITICAL):
    *   **Primary Font**: Identify the primary font used for headlines/logos (or the closest Google Font match if custom). Is it a Serif, Sans-Serif, Script, or Display font?
    *   **Secondary Font**: Identify the secondary font used for body text or subheadings.
    *   **Weights & Styles**: meaningful details like "Bold uppercase for headlines", "Light elegant serif for body", "Wide tracking/letter-spacing".
    *   **Do's & Don'ts**: explicit instructions on what font styles to AVOID (e.g., "Never use Comic Sans", "Avoid script fonts", "No drop shadows on text").

5. **COMPOSITION PATTERNS**: How are elements arranged? Clean layouts? Busy? Centered or asymmetric?

6. **MOOD & ATMOSPHERE**: Professional, friendly, luxurious, energetic, calm?

Return a SINGLE PARAGRAPH that can be directly used as a generation prompt prefix. Start with "Create content in this brand style:" and describe how to replicate this exact visual identity.

Be specific about colors (use hex codes if visible), logo placement, and especially TYPOGRAPHY. The goal is that AI-generated images using this prompt will look like they belong to the same brand.

IMPORTANT: Focus on visual elements that can be replicated. Don't describe what the images show, describe HOW they look visually."""


def _build_fallback_style_prompt(brand_colors: Optional[List[str]] = None) -> str:
    """Build a fallback style prompt if extraction fails."""
    if brand_colors:
        colors_str = ", ".join(brand_colors)
        return f"Create content using these brand colors: {colors_str}. Ensure visual consistency with the brand identity."
    return ""


def get_enhanced_generation_prompt(
    user_prompt: str,
    style_prompt: str,
    logo_instruction: str = ""
) -> str:
    """
    Combine the extracted style prompt with the user's content request.
    
    Args:
        user_prompt: The user's original content request
        style_prompt: The extracted style prompt from brand analysis
        logo_instruction: Additional logo enforcement instructions
    
    Returns:
        Enhanced prompt for generation
    """
    parts = []
    
    if style_prompt:
        parts.append(f"=== BRAND STYLE GUIDE ===\n{style_prompt}\n===========================")
    
    if logo_instruction:
        parts.append(logo_instruction)
    
    parts.append(f"\n=== CONTENT REQUEST ===\n{user_prompt}")
    parts.append("\n\nIMPORTANT: Ensure all text in the generated media is in English and free of spelling mistakes.")
    
    return "\n".join(parts)
