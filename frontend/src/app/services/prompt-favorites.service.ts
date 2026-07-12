import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { PromptMetadata } from './brand.service';

export interface PromptFavorite {
  id: number;
  title: string;
  prompt_text: string;
  prompt_metadata: PromptMetadata | null;
  source_job_id: number | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreatePromptFavoriteRequest {
  title: string;
  prompt_text: string;
  prompt_metadata?: PromptMetadata | null;
  source_job_id?: number | null;
}

export interface UpdatePromptFavoriteRequest {
  title?: string;
  prompt_text?: string;
  prompt_metadata?: PromptMetadata | null;
}

@Injectable({ providedIn: 'root' })
export class PromptFavoritesService {
  private apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  listFavorites(): Observable<PromptFavorite[]> {
    return this.http.get<PromptFavorite[]>(`${this.apiUrl}/prompts/favorites`);
  }

  createFavorite(payload: CreatePromptFavoriteRequest): Observable<PromptFavorite> {
    return this.http.post<PromptFavorite>(`${this.apiUrl}/prompts/favorites`, payload);
  }

  updateFavorite(id: number, payload: UpdatePromptFavoriteRequest): Observable<PromptFavorite> {
    return this.http.put<PromptFavorite>(`${this.apiUrl}/prompts/favorites/${id}`, payload);
  }

  deleteFavorite(id: number): Observable<{ deleted: boolean; id: number }> {
    return this.http.delete<{ deleted: boolean; id: number }>(`${this.apiUrl}/prompts/favorites/${id}`);
  }
}
