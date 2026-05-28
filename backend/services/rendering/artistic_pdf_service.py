import os
from jinja2 import Environment, FileSystemLoader
import datetime
from weasyprint import HTML

class ArtisticPDFService:
    def __init__(self, templates_dir="templates", output_dir="outputs/artistic_pdf"):
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_pdf(self, job_id, slides_data, brand_dna=None):
        """
        Genera un PDF completo de alta fidelidad capturando cada slide usando WeasyPrint.
        """
        print(f"  [ArtisticPDF] Starting WeasyPrint Render for Job {job_id}...")
        
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

        # Generar PDF
        HTML(string=full_html, base_url=".").write_pdf(pdf_path)
        
        print(f"  [ArtisticPDF] WeasyPrint PDF Generated: {pdf_path}")
        return pdf_path

# Singleton instance
artistic_pdf_service = ArtisticPDFService()
