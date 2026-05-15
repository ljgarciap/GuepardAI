
import os
import asyncio
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
import datetime

class ArtisticPDFService:
    def __init__(self, templates_dir="templates", output_dir="outputs/artistic_pdf"):
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        os.makedirs(self.output_dir, exist_ok=True)

    async def render_slide_to_html(self, slide_data, template_name="artistic_v1.html"):
        """Renderiza un slide individual a HTML usando Jinja2."""
        template = self.env.get_template(template_name)
        return template.render(**slide_data)

    async def generate_pdf(self, job_id, slides_data, brand_dna=None):
        """
        Genera un PDF completo de alta fidelidad capturando cada slide con Playwright.
        """
        print(f"  [ArtisticPDF] Starting High-Fidelity Render for Job {job_id}...")
        
        # DEFINICIÓN INICIAL (Blindaje total contra UnboundLocalError)
        agency_logo_b64 = ""
        
        try:
            agency_logo_path = "/app/backend/assets/agency/L-founders_logo.png"
            if not os.path.exists(agency_logo_path):
                agency_logo_path = "backend/assets/agency/L-founders_logo.png"
            
            if os.path.exists(agency_logo_path):
                import base64
                with open(agency_logo_path, "rb") as f:
                    agency_logo_b64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        except Exception as e:
            print(f"  [ArtisticPDF] Warning: Could not encode agency logo: {e}")

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            
            pdf_filename = f"Portfolio_{job_id}_{int(datetime.datetime.now().timestamp())}.pdf"
            pdf_path = os.path.join(self.output_dir, pdf_filename)
            
            common_data = {
                "primary_color": brand_dna.primary_color if brand_dna else "#002D62",
                "secondary_color": brand_dna.secondary_color if brand_dna else "#E31837",
                "agency_logo": agency_logo_b64
            }

            # Renderizar HTML usando el template base que itera sobre slides
            template = self.env.get_template("pdf_base.html")
            full_html = template.render(slides=slides_data, **common_data)

            await page.set_content(full_html)
            # Esperar a que las fuentes y gradientes carguen
            await asyncio.sleep(1) 
            
            await page.pdf(path=pdf_path, 
                          width="1280px", 
                          height="720px", 
                          print_background=True,
                          display_header_footer=False)
            
            await browser.close()
            print(f"  [ArtisticPDF] PDF Generated: {pdf_path}")
            return pdf_path

# Singleton instance
artistic_pdf_service = ArtisticPDFService()
