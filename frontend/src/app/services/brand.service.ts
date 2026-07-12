import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface PortfolioItem {
  id: number;
  filename: string;
  display_name: string;
  created_at: string;
  brand_id: number | null;
  rating: number | null;
  comment: string | null;
  has_prompt: boolean;
}

export interface PortfolioDetail {
  id: number;
  filename: string;
  display_name: string;
  created_at: string;
  brand_id: number | null;
  prompt: string;
  prompt_metadata: PromptMetadata | null;
}

export interface PromptIntent {
  slug: string;
  label: string;
  expected_tone: string;
  expected_duration_label: string;
  narrative_style: string;
  visual_density: string;
  preferred_layouts: string[];
}

export interface PromptMetadata {
  intent_slug?: string;
  objective?: string;
  tone?: string;
  audience?: string;
  slide_type?: string;
  story?: string;
  visual_rules?: string;
  output_format?: string;
  no_buzzwords?: boolean;
}

export interface PortfolioPage {
  items: PortfolioItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PortfolioFilters {
  search?: string;
  dateFrom?: string;   // YYYY-MM-DD
  dateTo?: string;     // YYYY-MM-DD
  page?: number;
  pageSize?: number;
}

export interface TemplateMergeHistoryItem {
  id: number;
  filename: string;
  display_name: string;
  created_at: string;
  brand_id: number | null;
}

export interface TemplateMergeHistoryPage {
  items: TemplateMergeHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface TemplateMergeJobDetail {
  job_id: number;
  display_name: string | null;
  prompt: string;
}

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

  getLibraryPortfolios(brandId?: number, filters?: PortfolioFilters): Observable<PortfolioPage> {
    let params = new HttpParams();
    if (brandId) params = params.set('brand_id', brandId);
    if (filters?.search?.trim()) params = params.set('search', filters.search.trim());
    if (filters?.dateFrom) params = params.set('date_from', filters.dateFrom);
    if (filters?.dateTo) params = params.set('date_to', filters.dateTo);
    params = params.set('page', filters?.page ?? 1);
    params = params.set('page_size', filters?.pageSize ?? 12);
    return this.http.get<PortfolioPage>(`${this.apiUrl}/library/portfolios`, { params });
  }

  renamePortfolio(jobId: number, displayName: string): Observable<{ id: number; display_name: string; filename: string }> {
    return this.http.patch<{ id: number; display_name: string; filename: string }>(
      `${this.apiUrl}/library/portfolios/${jobId}`,
      { display_name: displayName }
    );
  }

  deletePortfolio(jobId: number): Observable<{ deleted: boolean; id: number }> {
    return this.http.delete<{ deleted: boolean; id: number }>(`${this.apiUrl}/library/portfolios/${jobId}`);
  }

  getPortfolioDetail(jobId: number): Observable<PortfolioDetail> {
    return this.http.get<PortfolioDetail>(`${this.apiUrl}/library/portfolios/${jobId}`);
  }

  getPromptIntents(): Observable<PromptIntent[]> {
    return this.http.get<PromptIntent[]>(`${this.apiUrl}/config/prompt-intents`);
  }

  generatePresentation(req: {
    prompt: string, 
    style_filename: string, 
    knowledge_filename: string, 
    region?: string, 
    brand_id?: number, 
    allow_ai_images?: boolean,
    output_format?: string,
    tier?: string,
    prompt_metadata?: PromptMetadata
  }): Observable<any> {
    return this.http.post(`${this.apiUrl}/presentations/generate`, req);
  }

  downloadPortfolio(jobId: number): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/generation/download/${jobId}`, { responseType: 'blob' });
  }

  getTemplateMergeHistory(brandId?: number, filters?: PortfolioFilters): Observable<TemplateMergeHistoryPage> {
    let params = new HttpParams();
    if (brandId) params = params.set('brand_id', brandId);
    if (filters?.search?.trim()) params = params.set('search', filters.search.trim());
    if (filters?.dateFrom) params = params.set('date_from', filters.dateFrom);
    if (filters?.dateTo) params = params.set('date_to', filters.dateTo);
    params = params.set('page', filters?.page ?? 1);
    params = params.set('page_size', filters?.pageSize ?? 12);
    return this.http.get<TemplateMergeHistoryPage>(`${this.apiUrl}/template-merge/jobs`, { params });
  }

  renameTemplateMergeJob(jobId: number, displayName: string): Observable<{ id: number; display_name: string; filename: string }> {
    return this.http.patch<{ id: number; display_name: string; filename: string }>(
      `${this.apiUrl}/template-merge/jobs/${jobId}`,
      { display_name: displayName }
    );
  }

  deleteTemplateMergeJob(jobId: number): Observable<{ deleted: boolean; id: number }> {
    return this.http.delete<{ deleted: boolean; id: number }>(`${this.apiUrl}/template-merge/jobs/${jobId}`);
  }

  getTemplateMergeJobDetail(jobId: number): Observable<TemplateMergeJobDetail> {
    return this.http.get<TemplateMergeJobDetail>(`${this.apiUrl}/template-merge/jobs/${jobId}`);
  }

  resetDatabase(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/admin/reset-db`);
  }

  submitFeedback(jobId: number, rating: number, comment?: string, questionKey: string = 'presentation_satisfaction'): Observable<any> {
    return this.http.post(`${this.apiUrl}/presentations/${jobId}/feedback`, {
      question_key: questionKey,
      rating,
      comment
    });
  }

  getFeedback(jobId: number): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/presentations/${jobId}/feedback`);
  }

  getFooters(): Observable<any> {
    return this.http.get(`${this.apiUrl}/footers`);
  }

  createFooter(name: string, text?: string, disclaimer?: string, logoLight?: File, logoDark?: File, id?: number): Observable<any> {
    const formData = new FormData();
    if (id !== undefined && id !== null) {
      formData.append('id', id.toString());
    }
    formData.append('name', name);
    if (text) formData.append('text', text);
    if (disclaimer) formData.append('disclaimer', disclaimer);
    if (logoLight) formData.append('logo_light', logoLight);
    if (logoDark) formData.append('logo_dark', logoDark);
    
    return this.http.post(`${this.apiUrl}/footers`, formData);
  }

  selectFooter(footerId: number): Observable<any> {
    return this.http.put(`${this.apiUrl}/footers/${footerId}/select`, {});
  }

  deleteFooter(footerId: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/footers/${footerId}`);
  }

  toggleFooterGlobal(enabled: boolean): Observable<any> {
    return this.http.put(`${this.apiUrl}/footers/toggle?enabled=${enabled}`, {});
  }
}
