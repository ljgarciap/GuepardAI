import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class BrandService {
  private apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  /**
   * Uploads an asset for ingestion with governance.
   */
  uploadBrandAsset(file: File, ingestionType: string, visibilityScope: string = 'exclusive', brandId?: number, manualTags: string = ''): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingestion_type', ingestionType);
    formData.append('visibility_scope', visibilityScope);
    if (brandId) formData.append('brand_id', brandId.toString());
    if (manualTags) formData.append('manual_tags', manualTags);
    
    return this.http.post(`${this.apiUrl}/brand/upload`, formData);
  }

  getBrands(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/brands`);
  }

  createBrand(name: string, about?: string, coreValue?: string, logo?: File): Observable<any> {
    const formData = new FormData();
    formData.append('name', name);
    if (about) formData.append('about', about);
    if (coreValue) formData.append('core_value', coreValue);
    if (logo) formData.append('logo', logo);
    
    return this.http.post(`${this.apiUrl}/brands`, formData);
  }

  updateBrand(brandId: number, name: string, about?: string, coreValue?: string, logo?: File): Observable<any> {
    const formData = new FormData();
    formData.append('name', name);
    if (about) formData.append('about', about);
    if (coreValue) formData.append('core_value', coreValue);
    if (logo) formData.append('logo', logo);
    
    return this.http.put(`${this.apiUrl}/brands/${brandId}`, formData);
  }

  getIngestionStatus(filename: string, type: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/ingestion/status/${filename}?ingestion_type=${type}`);
  }

  getGenerationStatus(jobId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/generation/status/${jobId}`);
  }

  getAvailableStyles(brandId?: number): Observable<any> {
    const url = brandId ? `${this.apiUrl}/available-styles?brand_id=${brandId}` : `${this.apiUrl}/available-styles`;
    return this.http.get(url);
  }

  getAvailableKnowledge(brandId?: number): Observable<any> {
    const url = brandId ? `${this.apiUrl}/available-knowledge?brand_id=${brandId}` : `${this.apiUrl}/available-knowledge`;
    return this.http.get(url);
  }

  getAvailableDialects(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/available-dialects`);
  }

  getLibraryImages(brandId?: number): Observable<any[]> {
    const url = brandId ? `${this.apiUrl}/library/images?brand_id=${brandId}` : `${this.apiUrl}/library/images`;
    return this.http.get<any[]>(url);
  }

  getLibraryBlueprints(brandId?: number): Observable<any[]> {
    const url = brandId ? `${this.apiUrl}/library/blueprints?brand_id=${brandId}` : `${this.apiUrl}/library/blueprints`;
    return this.http.get<any[]>(url);
  }

  getLibraryKnowledge(brandId?: number): Observable<any[]> {
    const url = brandId ? `${this.apiUrl}/library/knowledge?brand_id=${brandId}` : `${this.apiUrl}/library/knowledge`;
    return this.http.get<any[]>(url);
  }

  getLibraryPortfolios(brandId?: number): Observable<any[]> {
    const url = brandId ? `${this.apiUrl}/library/portfolios?brand_id=${brandId}` : `${this.apiUrl}/library/portfolios`;
    return this.http.get<any[]>(url);
  }

  generatePresentation(req: {
    prompt: string, 
    style_filename: string, 
    knowledge_filename: string, 
    region?: string, 
    brand_id?: number, 
    allow_ai_images?: boolean,
    output_format?: string
  }): Observable<any> {
    return this.http.post(`${this.apiUrl}/presentations/generate`, req);
  }

  resetDatabase(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/admin/reset-db`);
  }
}
