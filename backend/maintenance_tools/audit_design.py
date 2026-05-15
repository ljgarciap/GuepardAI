from database import SessionLocal
import models
import json

def audit_jobs(job_ids):
    db = SessionLocal()
    for j_id in job_ids:
        job = db.query(models.GenerationJob).get(j_id)
        if not job:
            print(f"Job {j_id} not found.")
            continue
            
        print(f"\n{'='*60}")
        print(f"AUDIT REPORT: JOB {j_id} ({job.client_name})")
        print(f"{'='*60}")
        
        slides = db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id==j_id).order_by(models.PresentationSlide.slide_number).all()
        
        for s in slides:
            planning = s.planning_json or {}
            ad = planning.get("art_director", {})
            layout = ad.get("suggested_layout_override") or s.layout_slug
            
            print(f"\n[Slide {s.slide_number}] Title: {s.title}")
            print(f"  - Final Layout: {layout}")
            print(f"  - Assigned Image: {s.assigned_image}")
            
            # Check for Custom Canvas
            canvas = ad.get("canvas_elements", [])
            if canvas:
                print(f"  - CUSTOM CANVAS DETECTED ({len(canvas)} elements):")
                for el in canvas:
                    print(f"    * {el.get('type')}: {el.get('path') or el.get('text')[:20]} at ({el.get('x')}, {el.get('y')})")
            
            # Check for Reasoning
            reasoning = ad.get("visual_reasoning", "None")
            print(f"  - Reasoning: {reasoning[:100]}...")

    db.close()

if __name__ == "__main__":
    audit_jobs([61, 62])
