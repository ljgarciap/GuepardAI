import datetime
import os

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML


class ArtisticPDFService:
    def __init__(self, templates_dir="templates", output_dir="outputs/artistic_pdf"):
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        os.makedirs(self.output_dir, exist_ok=True)

    def _asset_to_data_uri(self, raw_path):
        if not raw_path:
            return ""

        candidates = []
        if os.path.isabs(raw_path):
            candidates.append(raw_path)
        else:
            candidates.extend([
                raw_path,
                os.path.join("uploads", raw_path),
                os.path.join("backend", "uploads", raw_path),
                os.path.join("/app", raw_path),
                os.path.join("/app", "uploads", raw_path),
            ])

        for path in candidates:
            if os.path.exists(path):
                try:
                    import base64
                    ext = os.path.splitext(path)[1].lower().replace(".", "") or "png"
                    if ext == "jpg":
                        ext = "jpeg"
                    with open(path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode()
                    return f"data:image/{ext};base64,{encoded}"
                except Exception as e:
                    print(f"  [ArtisticPDF] Warning: Could not encode asset {path}: {e}")
        return raw_path

    def _load_agency_logo(self):
        try:
            agency_logo_path = "/app/backend/assets/agency/L-founders_logo.png"
            if not os.path.exists(agency_logo_path):
                agency_logo_path = "backend/assets/agency/L-founders_logo.png"
            return self._asset_to_data_uri(agency_logo_path)
        except Exception as e:
            print(f"  [ArtisticPDF] Warning: Could not encode agency logo: {e}")
            return ""

    def generate_pdf(self, job_id, slides_data, brand_dna=None):
        """
        Legacy artistic PDF renderer updated to use Playwright headless for Tailwind CDN support.
        """
        print(f"  [ArtisticPDF] Starting Playwright Render for Job {job_id}...")

        pdf_filename = f"Portfolio_{job_id}_{int(datetime.datetime.now().timestamp())}.pdf"
        pdf_path = os.path.join(self.output_dir, pdf_filename)

        # Base64 encode images for local rendering
        for slide in slides_data:
            slide["primary_image"] = self._asset_to_data_uri(slide.get("primary_image") or slide.get("hero_image"))
            slide["bullet_icon"] = self._asset_to_data_uri(slide.get("bullet_icon"))

        common_data = {
            "primary_color": getattr(brand_dna, "primary_color", "#002D62") if brand_dna else "#002D62",
            "secondary_color": getattr(brand_dna, "secondary_color", "#E31837") if brand_dna else "#E31837",
            "agency_logo": self._load_agency_logo(),
        }

        template = self.env.get_template("pdf_base.html")
        full_html = template.render(slides=slides_data, **common_data)

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu"
                    ]
                )
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                page.set_content(full_html, wait_until="networkidle")
                
                # Wait for Tailwind CDN to compile styles
                try:
                    page.wait_for_function("document.getElementById('tailwind-style') !== null", timeout=5000)
                    page.wait_for_timeout(500) # Give it an extra half second to settle the paint
                except Exception as wait_e:
                    print(f"  [ArtisticPDF] Tailwind wait timeout: {wait_e}")
                    
                page.pdf(
                    path=pdf_path,
                    width="1280px",
                    height="720px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
                browser.close()
        except Exception as e:
            print(f"  [ArtisticPDF] Playwright rendering failed: {e}")
            raise e

        print(f"  [ArtisticPDF] Playwright PDF Generated: {pdf_path}")
        return pdf_path

    def generate_premium_pdf(self, job_id, slides_data, brand_dna=None, patterns=None, evaluation=None):
        """
        Premium HTML/CSS PDF renderer backed by Playwright/Chromium.
        This is intentionally separate from the PPTX painter pipeline.
        """
        print(f"  [PremiumPDF] Starting Playwright Render for Job {job_id}...")

        pdf_filename = f"Premium_Portfolio_{job_id}_{int(datetime.datetime.now().timestamp())}.pdf"
        pdf_path = os.path.join(self.output_dir, pdf_filename)

        for slide in slides_data:
            slide["hero_image"] = self._asset_to_data_uri(slide.get("hero_image"))
            slide["accent_image"] = self._asset_to_data_uri(slide.get("accent_image"))
            slide["logo_image"] = self._asset_to_data_uri(slide.get("logo_image"))

        common_data = {
            "primary_color": getattr(brand_dna, "primary_color", "#002D62") if brand_dna else "#002D62",
            "secondary_color": getattr(brand_dna, "secondary_color", "#E31837") if brand_dna else "#E31837",
            "background_color": getattr(brand_dna, "background_color", "#FFFFFF") if brand_dna else "#FFFFFF",
            "text_main_color": getattr(brand_dna, "text_main_color", "#111111") if brand_dna else "#111111",
            "primary_font": getattr(brand_dna, "primary_font", "Arial") if brand_dna else "Arial",
            "agency_logo": self._load_agency_logo(),
            "patterns": patterns or [],
            "evaluation": evaluation or {},
        }

        template = self.env.get_template("premium_pdf.html")
        full_html = template.render(slides=slides_data, **common_data)

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu"
                    ]
                )
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                page.set_content(full_html, wait_until="networkidle")
                page.pdf(
                    path=pdf_path,
                    width="1280px",
                    height="720px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
                browser.close()
        except Exception as e:
            print(f"  [PremiumPDF] Playwright rendering failed: {e}")
            raise e

        print(f"  [PremiumPDF] PDF Generated: {pdf_path}")
        return pdf_path


artistic_pdf_service = ArtisticPDFService()
