import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

/**
 * artistic-v2.service.ts — Artistic Generation Engine v2 (Phase 4).
 * docs/specs/artistic-generation-v2.md
 *
 * Deliberately self-contained: does not import BrandService or reuse any of
 * its methods, even where an endpoint is generic enough to share (job status
 * polling) — the isolation constraint this whole feature is built around
 * ("no shared component is edited in place to become v2") extends to the
 * frontend service layer too, not just backend code.
 */

export interface EligibleBrand {
  id: number;
  name: string;
}

export interface ArtisticV2GenerateRequest {
  brand_id: number;
  prompt: string;
  style_filename?: string;
  knowledge_filename?: string;
  region?: string;
  allow_ai_images?: boolean;
  output_format?: string;
  tier?: string;
}

export interface GenerationStatus {
  id: number;
  status: string;
  progress: number;
  current_step: string;
  qa_forced: boolean;
  download_url: string | null;
}

@Injectable({ providedIn: 'root' })
export class ArtisticV2Service {
  private http = inject(HttpClient);
  private apiUrl = environment.apiUrl;

  getEligibleBrands(): Observable<{ brands: EligibleBrand[] }> {
    return this.http.get<{ brands: EligibleBrand[] }>(`${this.apiUrl}/artistic-v2/eligible-brands`);
  }

  generate(req: ArtisticV2GenerateRequest): Observable<{ job_id: number; status: string; engine_version: string }> {
    return this.http.post<{ job_id: number; status: string; engine_version: string }>(
      `${this.apiUrl}/artistic-v2/generate`, req
    );
  }

  // Reuses the existing, engine_version-agnostic status endpoint directly
  // (not through BrandService) — it was never v1-specific, it just reads a
  // GenerationJob by id, so duplicating this one GET keeps this service
  // free of any dependency on v1's own service layer.
  getGenerationStatus(jobId: number): Observable<GenerationStatus> {
    return this.http.get<GenerationStatus>(`${this.apiUrl}/generation/status/${jobId}`);
  }

  // The v1 counterpart for the side-by-side comparison view. Calls the
  // existing /api/presentations/generate endpoint directly (same one
  // GeneratorComponent uses via BrandService) — reading a stable, unmodified
  // v1 endpoint is not the same as editing v1 code, and duplicating this one
  // POST keeps this whole feature in a single self-contained service file.
  generateV1(req: ArtisticV2GenerateRequest): Observable<{ job_id: number; status: string }> {
    return this.http.post<{ job_id: number; status: string }>(`${this.apiUrl}/presentations/generate`, req);
  }

  // The download route requires a Bearer token (Depends(get_current_user)) —
  // a plain <a href> is a raw browser navigation that never carries the
  // Authorization header the auth interceptor attaches to HttpClient calls,
  // so it 401s silently. GeneratorComponent already solves this correctly
  // (BrandService.downloadPortfolio + triggerBlobDownload) — same fix here,
  // duplicated rather than imported to keep this service self-contained.
  downloadPortfolio(jobId: number): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/generation/download/${jobId}`, { responseType: 'blob' });
  }
}
