import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class BrandService {
  private apiUrl = 'http://localhost:8001/api';

  constructor(private http: HttpClient) {}

  /**
   * Uploads an asset for ingestion.
   * @param ingestionType 'visual_dna' | 'artistic' | 'knowledge'
   * @param file PDF or PPTX document
   */
  uploadBrandAsset(file: File, ingestionType: 'brand_style' | 'visual_dna' | 'artistic' | 'knowledge'): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingestion_type', ingestionType);
    
    return this.http.post(`${this.apiUrl}/brand/upload`, formData);
  }

  getIngestionStatus(filename: string, type: 'brand_style' | 'visual_dna' | 'artistic' | 'knowledge'): Observable<any> {
    return this.http.get(`${this.apiUrl}/ingestion/status/${filename}?ingestion_type=${type}`);
  }

  getAvailableStyles(): Observable<any> {
    return this.http.get(`${this.apiUrl}/available-styles`);
  }

  getAvailableKnowledge(): Observable<any> {
    return this.http.get(`${this.apiUrl}/available-knowledge`);
  }

  generatePresentation(styleFilename: string, knowledgeFilename: string, prompt: string, region: string = 'LATAM'): Observable<Blob> {
    return this.http.post(`${this.apiUrl}/presentations/generate`, 
      { 
        style_filename: styleFilename, 
        knowledge_filename: knowledgeFilename, 
        prompt: prompt, 
        region: region 
      }, 
      { responseType: 'blob' }
    );
  }

  resetDatabase(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/admin/reset-db`);
  }
}
