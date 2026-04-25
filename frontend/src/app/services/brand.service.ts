import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class BrandService {
  private apiUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) {}

  /**
   * Uploads an asset for ingestion.
   */
  uploadBrandAsset(file: File, ingestionType: string): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingestion_type', ingestionType);
    return this.http.post(`${this.apiUrl}/brand/upload`, formData);
  }

  getIngestionStatus(filename: string, type: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/ingestion/status/${filename}?ingestion_type=${type}`);
  }

  getGenerationStatus(jobId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/generation/status/${jobId}`);
  }

  getAvailableStyles(): Observable<any> {
    return this.http.get(`${this.apiUrl}/available-styles`);
  }

  getAvailableKnowledge(): Observable<any> {
    return this.http.get(`${this.apiUrl}/available-knowledge`);
  }

  generatePresentation(prompt: string, styleFilename: string, knowledgeFilename: string, region: string = 'LATAM'): Observable<any> {
    return this.http.post(`${this.apiUrl}/presentations/generate`, { 
      prompt, 
      style_filename: styleFilename, 
      knowledge_filename: knowledgeFilename, 
      region 
    });
  }

  resetDatabase(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/admin/reset-db`);
  }
}
